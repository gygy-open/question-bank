"""Composition Block 画布批量替换契约的聚焦测试。

覆盖:新增回填 id_map + 连续 sequence、更新保留身份 + 删除缺席、陈旧 revision 409
且无部分变更、跨 subject question 拒绝、服务端钉当前 question revision、
非 owner personal 404、非法 heading/answer_summary/page_break 422、一次 replace 一条 event。
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


async def _seed_question(db_session, *, subject_id: int, content_revision: int = 1) -> Question:
    doc = {"type": "doc", "content": [{"type": "paragraph"}]}
    q = Question(
        content=json.dumps(doc, ensure_ascii=False),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=subject_id,
        content_revision=content_revision,
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)
    return q


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


def _rich_doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _rich_text_block(text: str, temp_id: str) -> dict:
    return {"temp_id": temp_id, "block_type": "rich_text", "content": _rich_doc(text)}


@pytest.fixture
async def ctx(db_session):
    user = await _seed_user(db_session, username="alice")
    other = await _seed_user(db_session, username="bob")
    subject = await _seed_subject(db_session)
    subject2 = await _seed_subject(db_session, name="物理", slug="phys")
    return {"user": user, "other": other, "subject": subject, "subject2": subject2}


async def _create_shared_composition(client, sid: int, headers: dict) -> dict:
    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared",
        json={"title": "稿件"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# 新增:id_map + 连续 sequence
# --------------------------------------------------------------------------- #
async def test_replace_inserts_new_blocks_with_id_map_and_sequence(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={
            "expected_revision": 1,
            "blocks": [
                _rich_text_block("第一段", "t1"),
                {"temp_id": "t2", "block_type": "heading", "content": _rich_doc("标题"), "props": {"level": 2}},
                {"temp_id": "t3", "block_type": "page_break"},
            ],
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["revision"] == 2
    assert set(body["id_map"].keys()) == {"t1", "t2", "t3"}
    assert [b["sequence"] for b in body["blocks"]] == [0, 1, 2]
    assert [b["block_type"] for b in body["blocks"]] == ["rich_text", "heading", "page_break"]
    # id_map 指向真实返回的 block id。
    returned_ids = {b["id"] for b in body["blocks"]}
    assert set(body["id_map"].values()) == returned_ids


# --------------------------------------------------------------------------- #
# 更新保留身份 + 删除缺席
# --------------------------------------------------------------------------- #
async def test_replace_updates_identity_and_deletes_absent(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    first = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={
            "expected_revision": 1,
            "blocks": [_rich_text_block("A", "t1"), _rich_text_block("B", "t2")],
        },
        headers=h,
    )
    assert first.status_code == 200
    id1 = first.json()["id_map"]["t1"]
    id2 = first.json()["id_map"]["t2"]

    second = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={
            "expected_revision": 2,
            "blocks": [{"id": id1, "block_type": "rich_text", "content": _rich_doc("A2")}],
        },
        headers=h,
    )
    assert second.status_code == 200, second.text
    blocks = second.json()["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["id"] == id1  # 身份保留
    assert blocks[0]["sequence"] == 0
    assert blocks[0]["content"] == _rich_doc("A2")

    # id2 已删除:GET detail 不含它。
    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h
    )
    assert [b["id"] for b in detail.json()["blocks"]] == [id1]


# --------------------------------------------------------------------------- #
# 陈旧 revision → 409 且无部分变更
# --------------------------------------------------------------------------- #
async def test_stale_revision_conflicts_without_partial_change(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    ok = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={"expected_revision": 1, "blocks": [_rich_text_block("A", "t1")]},
        headers=h,
    )
    assert ok.status_code == 200
    id1 = ok.json()["id_map"]["t1"]

    stale = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={
            "expected_revision": 1,  # 已经是 2 了
            "blocks": [_rich_text_block("A", "t1"), _rich_text_block("B", "t2")],
        },
        headers=h,
    )
    assert stale.status_code == 409, stale.text

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h
    )
    body = detail.json()
    assert body["revision"] == 2  # 未再自增
    assert [b["id"] for b in body["blocks"]] == [id1]  # 未新增 B


# --------------------------------------------------------------------------- #
# question block:跨 subject 拒绝 + 服务端钉当前 revision
# --------------------------------------------------------------------------- #
async def test_question_block_pins_current_revision(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid, content_revision=7)

    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={
            "expected_revision": 1,
            "blocks": [
                {
                    "temp_id": "q1",
                    "block_type": "question",
                    "question_id": q.id,
                    "question_revision": 1,  # 客户端谎报,服务端应覆盖为 7
                }
            ],
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    block = r.json()["blocks"][0]
    assert block["question_id"] == q.id
    assert block["question_revision"] == 7


async def test_question_block_cross_subject_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    # 题目属于另一个学科。
    q = await _seed_question(db_session, subject_id=ctx["subject2"].id, content_revision=1)

    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={
            "expected_revision": 1,
            "blocks": [
                {"temp_id": "q1", "block_type": "question", "question_id": q.id, "question_revision": 1}
            ],
        },
        headers=h,
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# 非 owner personal → 404
# --------------------------------------------------------------------------- #
async def test_personal_composition_not_editable_by_others(client, ctx):
    sid = ctx["subject"].id
    owner = _auth(ctx["user"])

    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=personal",
        json={"title": "私有稿"},
        headers=owner,
    )
    assert r.status_code == 201, r.text
    comp = r.json()

    intruder = _auth(ctx["other"])
    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=personal",
        json={"expected_revision": 1, "blocks": [_rich_text_block("X", "t1")]},
        headers=intruder,
    )
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# 非法块 → 422
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_block",
    [
        {"temp_id": "t", "block_type": "heading", "content": None, "props": {"level": 1}},
        {"temp_id": "t", "block_type": "heading", "content": {"type": "doc", "content": [{"type": "paragraph"}, {"type": "paragraph"}]}, "props": {"level": 1}},
        {"temp_id": "t", "block_type": "heading", "content": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "x"}]}]}, "props": {"level": 5}},
        {"temp_id": "t", "block_type": "answer_summary", "props": {"mode": "wrong"}},
        {"temp_id": "t", "block_type": "answer_summary", "props": {"mode": "all", "extra": 1}},
        {"temp_id": "t", "block_type": "page_break", "content": {"type": "doc", "content": []}},
        {"temp_id": "t", "block_type": "rich_text", "content": {"type": "doc", "content": []}},
        {"id": 1, "temp_id": "t", "block_type": "page_break"},
        {"block_type": "page_break"},
    ],
)
async def test_invalid_blocks_rejected(client, ctx, bad_block):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={"expected_revision": 1, "blocks": [bad_block]},
        headers=h,
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# 一次 replace 一条 blocks_replaced 事件
# --------------------------------------------------------------------------- #
async def test_replace_writes_single_event(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/blocks?scope=shared",
        json={
            "expected_revision": 1,
            "batch_id": "batch-xyz",
            "blocks": [_rich_text_block("A", "t1")],
        },
        headers=h,
    )
    assert r.status_code == 200, r.text

    result = await db_session.execute(
        select(func.count())
        .select_from(CompositionEvent)
        .where(
            CompositionEvent.composition_id == comp["id"],
            CompositionEvent.event_type == "blocks_replaced",
        )
    )
    assert result.scalar_one() == 1

    ev = await db_session.execute(
        select(CompositionEvent).where(
            CompositionEvent.composition_id == comp["id"],
            CompositionEvent.event_type == "blocks_replaced",
        )
    )
    event = ev.scalars().first()
    assert event.batch_id == "batch-xyz"
    assert event.payload["added"] == 1
    assert event.composition_revision == 2
