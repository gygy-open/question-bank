"""Composition 定稿 (Version) 契约的聚焦测试。

覆盖:成功冻结完整题目、题目后续修改旧版本不变、expected_revision 冲突 409、
同一 revision 连续两次定稿 version_no 1/2 且 revision 不变、answer_summary all/before
resolved_question_ids(含去重保序)、跨 scope/subject/个人 owner 404、软删除稿可查看
版本但不能新定稿、列表不含 snapshot、一次定稿一条 finalized 事件。
"""
import json

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.composition import CompositionEvent
from app.models.question import Question, QuestionType
from app.models.subject import Subject
from app.models.user import User

API = "/api/v1"


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


def _rich_doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


async def _seed_full_question(
    db_session, *, subject_id: int, stem="1+1=?", content_revision: int = 1
) -> Question:
    """带 options/answer/analysis 的单选题,用于验证 snapshot 完整冻结。"""
    options = [
        {"id": "opt_a", "label": "A", "content": _rich_doc("2")},
        {"id": "opt_b", "label": "B", "content": _rich_doc("3")},
    ]
    q = Question(
        content=json.dumps(_rich_doc(stem), ensure_ascii=False),
        options=options,
        answer=json.dumps({"kind": "single_choice", "correct": "opt_a"}, ensure_ascii=False),
        analysis=json.dumps(_rich_doc("因为 1+1=2"), ensure_ascii=False),
        q_type=QuestionType.SINGLE_CHOICE,
        subject_id=subject_id,
        difficulty=3,
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
        json={"title": "稿件"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _set_blocks(client, sid, comp_id, headers, *, expected_revision, blocks, scope="shared"):
    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp_id}/blocks?scope={scope}",
        json={"expected_revision": expected_revision, "blocks": blocks},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _finalize(client, sid, comp_id, headers, *, expected_revision, label=None, scope="shared"):
    body = {"expected_revision": expected_revision}
    if label is not None:
        body["label"] = label
    return await client.post(
        f"{API}/subjects/{sid}/compositions/{comp_id}/versions?scope={scope}",
        json=body,
        headers=headers,
    )


# --------------------------------------------------------------------------- #
# 成功冻结完整题目
# --------------------------------------------------------------------------- #
async def test_finalize_freezes_full_question(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_full_question(db_session, subject_id=sid)
    comp = await _create_composition(client, sid, h)

    await _set_blocks(
        client, sid, comp["id"], h,
        expected_revision=1,
        blocks=[
            {"temp_id": "h1", "block_type": "heading", "content": _rich_doc("第一节"), "props": {"level": 2}},
            {"temp_id": "r1", "block_type": "rich_text", "content": _rich_doc("说明")},
            {"temp_id": "q1", "block_type": "question", "question_id": q.id},
            {"temp_id": "pb", "block_type": "page_break"},
        ],
    )

    r = await _finalize(client, sid, comp["id"], h, expected_revision=2, label="终稿")
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["version_no"] == 1
    assert version["source_revision"] == 2
    assert version["label"] == "终稿"

    snap = version["snapshot"]
    assert snap["schema_version"] == 1
    assert snap["composition_id"] == comp["id"]
    assert snap["source_revision"] == 2
    assert snap["subject_id"] == sid
    assert isinstance(snap["finalized_at"], str) and "T" in snap["finalized_at"]

    blocks = snap["blocks"]
    assert [b["block_type"] for b in blocks] == ["heading", "rich_text", "question", "page_break"]
    assert blocks[0]["props"]["level"] == 2

    qsnap = blocks[2]["question"]
    assert blocks[2]["question_id"] == q.id
    assert blocks[2]["question_revision"] == 1
    assert qsnap["id"] == q.id
    assert qsnap["q_type"] == "single_choice"
    assert qsnap["difficulty"] == 3
    assert qsnap["source"] == "seed"
    assert qsnap["content"] == _rich_doc("1+1=?")
    assert qsnap["answer"] == {"kind": "single_choice", "correct": "opt_a"}
    assert qsnap["options"][0]["id"] == "opt_a"
    assert qsnap["analysis"] == _rich_doc("因为 1+1=2")
    assert qsnap["thinking"] is None
    # 排除关系 / 权限 / 标签字段。
    assert "tags" not in qsnap and "knowledge_points" not in qsnap and "created_by" not in qsnap


# --------------------------------------------------------------------------- #
# 题目后续修改旧版本不变
# --------------------------------------------------------------------------- #
async def test_version_snapshot_is_immutable_after_question_edit(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_full_question(db_session, subject_id=sid, stem="原始题干")
    comp = await _create_composition(client, sid, h)
    await _set_blocks(
        client, sid, comp["id"], h,
        expected_revision=1,
        blocks=[{"temp_id": "q1", "block_type": "question", "question_id": q.id}],
    )
    r = await _finalize(client, sid, comp["id"], h, expected_revision=2)
    assert r.status_code == 201

    # 冻结后修改题目内容。
    q.content = json.dumps(_rich_doc("修改后的题干"), ensure_ascii=False)
    q.content_revision = 2
    db_session.add(q)
    await db_session.commit()

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/versions/1?scope=shared", headers=h
    )
    assert detail.status_code == 200, detail.text
    qsnap = detail.json()["snapshot"]["blocks"][0]["question"]
    assert qsnap["content"] == _rich_doc("原始题干")
    assert qsnap["content_revision"] == 1


# --------------------------------------------------------------------------- #
# expected_revision 冲突 409
# --------------------------------------------------------------------------- #
async def test_finalize_revision_mismatch_conflict(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    r = await _finalize(client, sid, comp["id"], h, expected_revision=999)
    assert r.status_code == 409, r.text


# --------------------------------------------------------------------------- #
# 同一 revision 两次定稿 → version_no 1/2 且 revision 不变
# --------------------------------------------------------------------------- #
async def test_two_finalizations_same_revision_increment_version_no(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)  # revision 1

    r1 = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r1.status_code == 201, r1.text
    assert r1.json()["version_no"] == 1

    r2 = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r2.status_code == 201, r2.text
    assert r2.json()["version_no"] == 2

    # composition.revision 不因定稿变化。
    got = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h)
    assert got.json()["revision"] == 1


# --------------------------------------------------------------------------- #
# answer_summary all / before resolved ids(去重保序)
# --------------------------------------------------------------------------- #
async def test_answer_summary_resolved_ids_all_and_before(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q1 = await _seed_full_question(db_session, subject_id=sid, stem="Q1")
    q2 = await _seed_full_question(db_session, subject_id=sid, stem="Q2")
    comp = await _create_composition(client, sid, h)
    await _set_blocks(
        client, sid, comp["id"], h,
        expected_revision=1,
        blocks=[
            {"temp_id": "b0", "block_type": "question", "question_id": q1.id},
            {"temp_id": "b1", "block_type": "answer_summary", "props": {"mode": "before"}},
            {"temp_id": "b2", "block_type": "question", "question_id": q2.id},
            {"temp_id": "b3", "block_type": "question", "question_id": q1.id},  # 重复
            {"temp_id": "b4", "block_type": "answer_summary", "props": {"mode": "all"}},
            {"temp_id": "b5", "block_type": "answer_summary", "props": {"mode": "before"}},
        ],
    )
    r = await _finalize(client, sid, comp["id"], h, expected_revision=2)
    assert r.status_code == 201, r.text
    blocks = r.json()["snapshot"]["blocks"]

    # seq1 before → 仅 q1
    assert blocks[1]["resolved_question_ids"] == [q1.id]
    # seq4 all → 整稿去重保序 [q1, q2]
    assert blocks[4]["resolved_question_ids"] == [q1.id, q2.id]
    # seq5 before → 之前出现的 q1, q2, q1 去重 → [q1, q2]
    assert blocks[5]["resolved_question_ids"] == [q1.id, q2.id]


async def test_answer_summary_empty_is_valid(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    await _set_blocks(
        client, sid, comp["id"], h,
        expected_revision=1,
        blocks=[{"temp_id": "s", "block_type": "answer_summary", "props": {"mode": "all"}}],
    )
    r = await _finalize(client, sid, comp["id"], h, expected_revision=2)
    assert r.status_code == 201, r.text
    assert r.json()["snapshot"]["blocks"][0]["resolved_question_ids"] == []


# --------------------------------------------------------------------------- #
# 跨 scope / subject / 个人 owner → 404
# --------------------------------------------------------------------------- #
async def test_versions_cross_scope_subject_owner_not_found(client, ctx):
    sid = ctx["subject"].id
    sid2 = ctx["subject2"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)  # shared under subject1
    await _finalize(client, sid, comp["id"], h, expected_revision=1)

    # 错误 scope。
    r = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}/versions?scope=personal", headers=h)
    assert r.status_code == 404
    # 错误 subject。
    r = await client.get(f"{API}/subjects/{sid2}/compositions/{comp['id']}/versions?scope=shared", headers=h)
    assert r.status_code == 404

    # 个人稿:非 owner 不可见。
    personal = await _create_composition(client, sid, h, scope="personal")
    hb = _auth(ctx["other"])
    r = await client.get(
        f"{API}/subjects/{sid}/compositions/{personal['id']}/versions?scope=personal", headers=hb
    )
    assert r.status_code == 404
    r = await _finalize(client, sid, personal["id"], hb, expected_revision=1, scope="personal")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# 软删除稿可查看版本但不能新定稿
# --------------------------------------------------------------------------- #
async def test_deleted_composition_allows_list_detail_but_not_finalize(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)  # revision 1
    r = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r.status_code == 201  # revision unchanged (still 1)

    # 软删除(revision → 2)。
    d = await client.delete(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared&expected_revision=1", headers=h
    )
    assert d.status_code == 204, d.text

    # list / detail 仍可查看历史版本。
    lst = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}/versions?scope=shared", headers=h)
    assert lst.status_code == 200
    assert len(lst.json()) == 1
    det = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}/versions/1?scope=shared", headers=h)
    assert det.status_code == 200

    # 但不能新定稿。
    r = await _finalize(client, sid, comp["id"], h, expected_revision=2)
    assert r.status_code == 409, r.text


# --------------------------------------------------------------------------- #
# 列表不含 snapshot
# --------------------------------------------------------------------------- #
async def test_version_list_excludes_snapshot(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    await _finalize(client, sid, comp["id"], h, expected_revision=1, label="v1")

    lst = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}/versions?scope=shared", headers=h)
    assert lst.status_code == 200
    items = lst.json()
    assert len(items) == 1
    assert "snapshot" not in items[0]
    assert items[0]["version_no"] == 1
    assert items[0]["label"] == "v1"


# --------------------------------------------------------------------------- #
# 一次定稿一条 finalized 事件,且 composition.revision 不变
# --------------------------------------------------------------------------- #
async def test_finalize_writes_single_event_without_revision_change(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)  # revision 1
    r = await _finalize(client, sid, comp["id"], h, expected_revision=1, label="标签")
    assert r.status_code == 201

    count = await db_session.scalar(
        select(func.count())
        .select_from(CompositionEvent)
        .where(
            CompositionEvent.composition_id == comp["id"],
            CompositionEvent.event_type == "finalized",
        )
    )
    assert count == 1

    event = (
        await db_session.execute(
            select(CompositionEvent).where(
                CompositionEvent.composition_id == comp["id"],
                CompositionEvent.event_type == "finalized",
            )
        )
    ).scalars().first()
    assert event.composition_revision == 1
    assert event.target_type == "version"
    assert event.target_id == "1"
    assert event.payload["version_no"] == 1
    assert event.payload["label"] == "标签"

    got = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h)
    assert got.json()["revision"] == 1
