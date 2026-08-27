"""Composition 定稿 (Version) 契约的聚焦测试(snapshot v2)。

覆盖:完整冻结题目、题目后续修改旧版本不变、expected_revision 冲突 409、
同一 revision 连续两次定稿 version_no 1/2 且 revision 不变、question_details module +
answer_item 配置冻结、跨 scope/subject/个人 owner 404、软删除稿可查看版本但不能新定稿、
列表不含 snapshot、一次定稿一条 finalized 事件。
"""
import json
import uuid
from urllib.parse import unquote

import pytest
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.composition import CompositionEvent, CompositionVersion
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


def _heading(text: str, level: int, nid: str | None = None) -> dict:
    return {
        "id": nid or _uid(), "node_kind": "block", "node_type": "heading",
        "content": _rich_doc(text), "props": {"level": level},
    }


def _page_break(nid: str | None = None) -> dict:
    return {"id": nid or _uid(), "node_kind": "block", "node_type": "page_break"}


def _question(question_id: int, nid: str | None = None) -> dict:
    return {"id": nid or _uid(), "node_kind": "block", "node_type": "question", "question_id": question_id}


def _module(scope: str, fields: dict | None = None, nid: str | None = None) -> dict:
    complete_fields = {
        "answer": True,
        "thinking": False,
        "analysis": False,
        "summary": False,
        **(fields or {}),
    }
    return {
        "id": nid or _uid(), "node_kind": "module", "node_type": "question_details",
        "props": {"scope": scope, "fields": complete_fields},
    }


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


async def _seed_full_question(db_session, *, subject_id: int, stem="1+1=?", content_revision: int = 1) -> Question:
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


async def _finalize(client, sid, comp_id, headers, *, expected_revision, label=None, scope="shared"):
    body = {"expected_revision": expected_revision}
    if label is not None:
        body["label"] = label
    return await client.post(
        f"{API}/subjects/{sid}/compositions/{comp_id}/versions?scope={scope}",
        json=body, headers=headers,
    )


async def _export(client, sid, comp_id, headers, *, version_no, fmt="docx", title=None, scope="shared"):
    body = {"format": fmt}
    if title is not None:
        body["title"] = title
    return await client.post(
        f"{API}/subjects/{sid}/compositions/{comp_id}/versions/{version_no}/export?scope={scope}",
        json=body, headers=headers,
    )


# --------------------------------------------------------------------------- #
# 成功冻结完整题目
# --------------------------------------------------------------------------- #
async def test_finalize_freezes_full_question(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_full_question(db_session, subject_id=sid)
    comp = await _create_composition(client, sid, h)

    qn = _uid()
    await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[_heading("第一节", 2), _rich_text("说明"), _question(q.id, qn), _page_break()],
    )

    r = await _finalize(client, sid, comp["id"], h, expected_revision=2, label="终稿")
    assert r.status_code == 201, r.text
    version = r.json()
    assert version["version_no"] == 1
    assert version["source_revision"] == 2
    assert version["label"] == "终稿"

    snap = version["snapshot"]
    assert snap["schema_version"] == 2
    assert snap["composition_id"] == comp["id"]
    assert snap["source_revision"] == 2
    assert snap["subject_id"] == sid
    assert isinstance(snap["finalized_at"], str) and "T" in snap["finalized_at"]

    nodes = snap["nodes"]
    assert [n["node_type"] for n in nodes] == ["heading", "rich_text", "question", "page_break"]
    assert nodes[0]["props"]["level"] == 2

    qnode = next(n for n in nodes if n["node_type"] == "question")
    qsnap = qnode["question"]
    assert qnode["question_id"] == q.id
    assert qnode["question_revision"] == 1
    assert qsnap["id"] == q.id
    assert qsnap["q_type"] == "single_choice"
    assert qsnap["difficulty"] == 3
    assert qsnap["source"] == "seed"
    assert qsnap["content"] == _rich_doc("1+1=?")
    assert qsnap["answer"] == {"kind": "single_choice", "correct": "opt_a"}
    assert qsnap["options"][0]["id"] == "opt_a"
    assert qsnap["analysis"] == _rich_doc("因为 1+1=2")
    assert qsnap["thinking"] is None
    assert "tags" not in qsnap and "knowledge_points" not in qsnap and "created_by" not in qsnap


# --------------------------------------------------------------------------- #
# numbering_enabled/scoring_enabled/question_display 冻结进 snapshot 顶层
# --------------------------------------------------------------------------- #
async def test_finalize_freezes_numbering_scoring_and_question_display(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_full_question(db_session, subject_id=sid)
    comp = await _create_composition(client, sid, h)

    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={
            "expected_revision": 1,
            "numbering_enabled": True,
            "scoring_enabled": True,
            "question_display": {"answer": True, "thinking": False, "analysis": True, "summary": False},
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["revision"] == 2

    await _put_nodes(client, sid, comp["id"], h, expected_revision=2, nodes=[_question(q.id)])

    r = await _finalize(client, sid, comp["id"], h, expected_revision=3)
    assert r.status_code == 201, r.text
    snap = r.json()["snapshot"]
    assert snap["numbering_enabled"] is True
    assert snap["scoring_enabled"] is True
    assert snap["question_display"] == {
        "answer": True, "thinking": False, "analysis": True, "summary": False,
    }


# --------------------------------------------------------------------------- #
# 题目后续修改旧版本不变
# --------------------------------------------------------------------------- #
async def test_version_snapshot_is_immutable_after_question_edit(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_full_question(db_session, subject_id=sid, stem="原始题干")
    comp = await _create_composition(client, sid, h)
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id)])
    r = await _finalize(client, sid, comp["id"], h, expected_revision=2)
    assert r.status_code == 201

    q.content = json.dumps(_rich_doc("修改后的题干"), ensure_ascii=False)
    q.content_revision = 2
    db_session.add(q)
    await db_session.commit()

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/versions/1?scope=shared", headers=h
    )
    assert detail.status_code == 200, detail.text
    nodes = detail.json()["snapshot"]["nodes"]
    qsnap = next(n for n in nodes if n["node_type"] == "question")["question"]
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
async def test_two_finalizations_same_revision_increment_version_no(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)

    r1 = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r1.status_code == 201, r1.text
    assert r1.json()["version_no"] == 1

    r2 = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r2.status_code == 201, r2.text
    assert r2.json()["version_no"] == 2

    got = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h)
    assert got.json()["revision"] == 1


# --------------------------------------------------------------------------- #
# question_details module + answer_item 配置冻结进 snapshot
# --------------------------------------------------------------------------- #
async def test_finalize_freezes_module_and_answer_items(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q1 = await _seed_full_question(db_session, subject_id=sid, stem="Q1")
    q2 = await _seed_full_question(db_session, subject_id=sid, stem="Q2")
    comp = await _create_composition(client, sid, h)

    qn1, qn2, mod = _uid(), _uid(), _uid()
    await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[_question(q1.id, qn1), _question(q2.id, qn2), _module("all", {"answer": True}, mod)],
    )
    r = await _finalize(client, sid, comp["id"], h, expected_revision=2)
    assert r.status_code == 201, r.text
    nodes = r.json()["snapshot"]["nodes"]

    module_snap = next(n for n in nodes if n["node_type"] == "question_details")
    assert module_snap["props"] == {
        "scope": "all",
        "fields": {
            "answer": True,
            "thinking": False,
            "analysis": False,
            "summary": False,
        },
    }

    answer_items = [n for n in nodes if n["node_type"] == "answer_item"]
    assert [a["source_question_node_id"] for a in answer_items] == [qn1, qn2]
    for a in answer_items:
        assert a["parent_id"] == mod
        assert a["props"]["included"] is True


# --------------------------------------------------------------------------- #
# 跨 scope / subject / 个人 owner → 404
# --------------------------------------------------------------------------- #
async def test_versions_cross_scope_subject_owner_not_found(client, ctx):
    sid = ctx["subject"].id
    sid2 = ctx["subject2"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    await _finalize(client, sid, comp["id"], h, expected_revision=1)

    r = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}/versions?scope=personal", headers=h)
    assert r.status_code == 404
    r = await client.get(f"{API}/subjects/{sid2}/compositions/{comp['id']}/versions?scope=shared", headers=h)
    assert r.status_code == 404

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
    comp = await _create_composition(client, sid, h)
    r = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r.status_code == 201

    d = await client.delete(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared&expected_revision=1", headers=h
    )
    assert d.status_code == 204, d.text

    lst = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}/versions?scope=shared", headers=h)
    assert lst.status_code == 200
    assert len(lst.json()) == 1
    det = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}/versions/1?scope=shared", headers=h)
    assert det.status_code == 200

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
    comp = await _create_composition(client, sid, h)
    r = await _finalize(client, sid, comp["id"], h, expected_revision=1, label="标签")
    assert r.status_code == 201

    count = await db_session.scalar(
        select(func.count()).select_from(CompositionEvent).where(
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


# --------------------------------------------------------------------------- #
# 版本导出:DOCX/LaTeX 成功
# --------------------------------------------------------------------------- #
async def test_export_version_docx_and_latex_succeed(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    q = await _seed_full_question(db_session, subject_id=sid)
    comp = await _create_composition(client, sid, h)
    await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id)])
    r = await _finalize(client, sid, comp["id"], h, expected_revision=2)
    assert r.status_code == 201, r.text

    r = await _export(client, sid, comp["id"], h, version_no=1, fmt="docx")
    assert r.status_code == 200, r.text
    assert len(r.content) > 0
    assert f'{comp["title"]}-v1.docx' in unquote(r.headers["content-disposition"])

    r = await _export(client, sid, comp["id"], h, version_no=1, fmt="latex")
    assert r.status_code == 200, r.text
    assert len(r.content) > 0
    assert f'{comp["title"]}-v1-latex.zip' in unquote(r.headers["content-disposition"])


async def test_export_uses_title_override(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    r = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r.status_code == 201

    r = await _export(client, sid, comp["id"], h, version_no=1, fmt="docx", title="自定义标题")
    assert r.status_code == 200, r.text
    assert "自定义标题-v1.docx" in unquote(r.headers["content-disposition"])


# --------------------------------------------------------------------------- #
# 版本导出:404(版本不存在 / 跨 scope 越权)、软删除稿仍可导出旧版本
# --------------------------------------------------------------------------- #
async def test_export_version_not_found_404(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    r = await _export(client, sid, comp["id"], h, version_no=99, fmt="docx")
    assert r.status_code == 404


async def test_export_cross_owner_not_found_404(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    hb = _auth(ctx["other"])
    personal = await _create_composition(client, sid, h, scope="personal")
    await _finalize(client, sid, personal["id"], h, expected_revision=1, scope="personal")
    r = await _export(client, sid, personal["id"], hb, version_no=1, fmt="docx", scope="personal")
    assert r.status_code == 404


async def test_export_allowed_after_composition_soft_deleted(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    r = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r.status_code == 201

    d = await client.delete(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared&expected_revision=1", headers=h
    )
    assert d.status_code == 204, d.text

    r = await _export(client, sid, comp["id"], h, version_no=1, fmt="docx")
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# 版本导出:损坏/未知 node_type 返回 422,附 node_id/node_type/version_no
# --------------------------------------------------------------------------- #
async def test_export_unsupported_node_type_returns_422(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    r = await _finalize(client, sid, comp["id"], h, expected_revision=1)
    assert r.status_code == 201
    version_no = r.json()["version_no"]

    version = (
        await db_session.execute(
            select(CompositionVersion).where(
                CompositionVersion.composition_id == comp["id"],
                CompositionVersion.version_no == version_no,
            )
        )
    ).scalars().first()
    corrupted = dict(version.snapshot)
    corrupted["nodes"] = [
        {"id": "bad1", "parent_id": None, "slot": None, "position": 0, "node_kind": "block", "node_type": "weird"}
    ]
    version.snapshot = corrupted
    db_session.add(version)
    await db_session.commit()

    r = await _export(client, sid, comp["id"], h, version_no=version_no, fmt="docx")
    assert r.status_code == 422, r.text
    body = r.json()["detail"]
    assert body["node_id"] == "bad1"
    assert body["node_type"] == "weird"
    assert body["version_no"] == version_no

    got = await client.get(f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h)
    assert got.json()["revision"] == 1
