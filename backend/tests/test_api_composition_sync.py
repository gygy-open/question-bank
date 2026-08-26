"""Question 节点版本状态 / 同步(冻结快照)契约的聚焦测试。

覆盖:新建 question 节点冻结快照、普通 replace 不隐式同步、改题重新钉快照、
question-revisions 状态(available / stale / deleted)、sync 单个/全部刷新 content+revision、
revision 一次 +1、一条 question_nodes_synced 事件、陈旧 revision 409、非 question 节点 422、
空/重复 node_ids 422、跨学科/软删题 422 全回滚、finalize 冻结的是节点快照(不查实时题)。
"""
import json
import uuid

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.composition import CompositionEvent
from app.models.question import Question, QuestionType
from app.models.subject import Subject
from app.models.user import User

API = "/api/v1"


def _uid() -> str:
    return str(uuid.uuid4())


def _rich_doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _rich_text(text: str, nid: str | None = None) -> dict:
    return {"id": nid or _uid(), "node_kind": "block", "node_type": "rich_text", "content": _rich_doc(text)}


def _question(question_id: int, nid: str | None = None) -> dict:
    return {"id": nid or _uid(), "node_kind": "block", "node_type": "question", "question_id": question_id}


async def _seed_user(db_session, *, username: str) -> User:
    user = User(username=username, full_name=username, hashed_password="x", is_active=True)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _seed_subject(db_session, *, name="数学", slug="math") -> Subject:
    subject = Subject(name=name, slug=slug)
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)
    return subject


async def _seed_question(db_session, *, subject_id: int, stem="题干", content_revision: int = 1) -> Question:
    q = Question(
        content=json.dumps(_rich_doc(stem), ensure_ascii=False),
        answer=json.dumps({"kind": "free_text"}, ensure_ascii=False),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=subject_id,
        difficulty=2,
        source="seed",
        content_revision=content_revision,
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)
    return q


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


@pytest.fixture
async def ctx(db_session):
    user = await _seed_user(db_session, username="alice")
    other = await _seed_user(db_session, username="bob")
    subject = await _seed_subject(db_session)
    subject2 = await _seed_subject(db_session, name="物理", slug="phys")
    return {"user": user, "other": other, "subject": subject, "subject2": subject2}


async def _create_composition(client, sid: int, headers: dict, scope="shared") -> dict:
    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope={scope}",
        json={"title": "稿件"}, headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _put_nodes(client, sid, comp_id, headers, *, expected_revision, nodes, scope="shared"):
    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp_id}/nodes?scope={scope}",
        json={"expected_revision": expected_revision, "nodes": nodes},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _roots(nodes: list) -> list:
    return sorted([n for n in nodes if n["parent_id"] is None], key=lambda n: n["position"])


async def _bump_question(db_session, q: Question, *, stem: str, revision: int) -> None:
    q.content = json.dumps(_rich_doc(stem), ensure_ascii=False)
    q.content_revision = revision
    db_session.add(q)
    await db_session.commit()


# --------------------------------------------------------------------------- #
# 新建 question 节点冻结当前内容快照
# --------------------------------------------------------------------------- #
async def test_new_question_node_freezes_content_snapshot(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_question(db_session, subject_id=sid, stem="原始", content_revision=3)
    comp = await _create_composition(client, sid, h)

    body = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id)])
    node = _roots(body["nodes"])[0]
    assert node["question_revision"] == 3
    assert node["content"]["q_type"] == "free_response"
    assert node["content"]["content"] == _rich_doc("原始")
    assert node["content"]["difficulty"] == 2
    assert "id" not in node["content"] and "content_revision" not in node["content"]


# --------------------------------------------------------------------------- #
# 普通 replace 不隐式同步:题号未变则保留旧快照与 revision
# --------------------------------------------------------------------------- #
async def test_plain_replace_preserves_snapshot_when_question_unchanged(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_question(db_session, subject_id=sid, stem="原始", content_revision=1)
    comp = await _create_composition(client, sid, h)

    qn = _uid()
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id, qn)])
    await _bump_question(db_session, q, stem="修改后", revision=5)

    body2 = await _put_nodes(client, sid, comp["id"], h, expected_revision=2, nodes=[_question(q.id, qn)])
    node = _roots(body2["nodes"])[0]
    assert node["id"] == qn
    assert node["question_revision"] == 1
    assert node["content"]["content"] == _rich_doc("原始")


# --------------------------------------------------------------------------- #
# 改题(question_id 变化)重新钉快照
# --------------------------------------------------------------------------- #
async def test_changing_question_id_repins_snapshot(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q1 = await _seed_question(db_session, subject_id=sid, stem="Q1", content_revision=1)
    q2 = await _seed_question(db_session, subject_id=sid, stem="Q2", content_revision=4)
    comp = await _create_composition(client, sid, h)

    qn = _uid()
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q1.id, qn)])
    body2 = await _put_nodes(client, sid, comp["id"], h, expected_revision=2, nodes=[_question(q2.id, qn)])
    node = _roots(body2["nodes"])[0]
    assert node["question_id"] == q2.id
    assert node["question_revision"] == 4
    assert node["content"]["content"] == _rich_doc("Q2")


# --------------------------------------------------------------------------- #
# question-revisions 状态:available / stale / deleted
# --------------------------------------------------------------------------- #
async def test_question_revisions_status(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q1 = await _seed_question(db_session, subject_id=sid, stem="Q1", content_revision=1)
    q2 = await _seed_question(db_session, subject_id=sid, stem="Q2", content_revision=1)
    comp = await _create_composition(client, sid, h)
    await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[_question(q1.id), _question(q2.id)],
    )

    await _bump_question(db_session, q1, stem="Q1改", revision=2)
    q2.deleted_at = func.now()
    db_session.add(q2)
    await db_session.commit()

    r = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/question-revisions?scope=shared", headers=h
    )
    assert r.status_code == 200, r.text
    by_id = {s["question_id"]: s for s in r.json()}
    assert by_id[q1.id] == {"question_id": q1.id, "current_revision": 2, "available": True}
    assert by_id[q2.id] == {"question_id": q2.id, "current_revision": None, "available": False}


async def test_question_revisions_empty_when_no_question_nodes(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    r = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/question-revisions?scope=shared", headers=h
    )
    assert r.status_code == 200
    assert r.json() == []


# --------------------------------------------------------------------------- #
# sync 刷新单个节点的 content + revision,revision 一次 +1,一条事件
# --------------------------------------------------------------------------- #
async def test_sync_single_node_refreshes_snapshot(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_question(db_session, subject_id=sid, stem="原始", content_revision=1)
    comp = await _create_composition(client, sid, h)
    qn = _uid()
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id, qn)])

    await _bump_question(db_session, q, stem="最新", revision=9)

    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/question-nodes/sync?scope=shared",
        json={"expected_revision": 2, "node_ids": [qn]}, headers=h,
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["revision"] == 3
    node = _roots(resp["nodes"])[0]
    assert node["question_revision"] == 9
    assert node["content"]["content"] == _rich_doc("最新")

    count = await db_session.scalar(
        select(func.count()).select_from(CompositionEvent).where(
            CompositionEvent.composition_id == comp["id"],
            CompositionEvent.event_type == "question_nodes_synced",
        )
    )
    assert count == 1


# --------------------------------------------------------------------------- #
# sync 全部:一个请求刷新多个节点,revision 只 +1
# --------------------------------------------------------------------------- #
async def test_sync_all_nodes_single_revision_bump(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q1 = await _seed_question(db_session, subject_id=sid, stem="A", content_revision=1)
    q2 = await _seed_question(db_session, subject_id=sid, stem="B", content_revision=1)
    comp = await _create_composition(client, sid, h)
    qn1, qn2 = _uid(), _uid()
    await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[_question(q1.id, qn1), _question(q2.id, qn2)],
    )

    await _bump_question(db_session, q1, stem="A2", revision=2)
    await _bump_question(db_session, q2, stem="B2", revision=3)

    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/question-nodes/sync?scope=shared",
        json={"expected_revision": 2, "node_ids": [qn1, qn2]}, headers=h,
    )
    assert r.status_code == 200, r.text
    resp = r.json()
    assert resp["revision"] == 3
    revs = {n["id"]: n["question_revision"] for n in _roots(resp["nodes"])}
    assert revs[qn1] == 2 and revs[qn2] == 3


# --------------------------------------------------------------------------- #
# sync:陈旧 revision 409(无部分变更)
# --------------------------------------------------------------------------- #
async def test_sync_stale_revision_conflict(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_question(db_session, subject_id=sid, content_revision=1)
    comp = await _create_composition(client, sid, h)
    qn = _uid()
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id, qn)])
    await _bump_question(db_session, q, stem="x", revision=2)

    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/question-nodes/sync?scope=shared",
        json={"expected_revision": 1, "node_ids": [qn]}, headers=h,
    )
    assert r.status_code == 409, r.text

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h
    )
    assert _roots(detail.json()["nodes"])[0]["question_revision"] == 1


# --------------------------------------------------------------------------- #
# sync:非 question 节点 → 422
# --------------------------------------------------------------------------- #
async def test_sync_non_question_node_rejected(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    rid = _uid()
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_rich_text("正文", rid)])
    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/question-nodes/sync?scope=shared",
        json={"expected_revision": 2, "node_ids": [rid]}, headers=h,
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# sync:空 / 重复 node_ids → 422(schema)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("node_ids", [[], ["dup", "dup"]])
async def test_sync_invalid_node_ids_rejected(client, ctx, node_ids):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/question-nodes/sync?scope=shared",
        json={"expected_revision": 1, "node_ids": node_ids}, headers=h,
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# sync:引用题目已软删除 → 422 且全回滚
# --------------------------------------------------------------------------- #
async def test_sync_deleted_question_rejected_and_rolls_back(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_question(db_session, subject_id=sid, content_revision=1)
    comp = await _create_composition(client, sid, h)
    qn = _uid()
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id, qn)])

    q.deleted_at = func.now()
    db_session.add(q)
    await db_session.commit()

    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/question-nodes/sync?scope=shared",
        json={"expected_revision": 2, "node_ids": [qn]}, headers=h,
    )
    assert r.status_code == 422, r.text
    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h
    )
    assert detail.json()["revision"] == 2  # 未自增


# --------------------------------------------------------------------------- #
# finalize 冻结节点快照(而非未同步的实时题);软删实时题仍可定稿
# --------------------------------------------------------------------------- #
async def test_finalize_uses_node_snapshot_not_live_question(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_question(db_session, subject_id=sid, stem="定稿前", content_revision=1)
    comp = await _create_composition(client, sid, h)
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id)])

    await _bump_question(db_session, q, stem="定稿后", revision=2)
    q.deleted_at = func.now()
    db_session.add(q)
    await db_session.commit()

    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/versions?scope=shared",
        json={"expected_revision": 2}, headers=h,
    )
    assert r.status_code == 201, r.text
    nodes = r.json()["snapshot"]["nodes"]
    qnode = next(n for n in nodes if n["node_type"] == "question")
    assert qnode["question"]["content"] == _rich_doc("定稿前")
    assert qnode["question"]["content_revision"] == 1
    assert qnode["question"]["id"] == q.id
