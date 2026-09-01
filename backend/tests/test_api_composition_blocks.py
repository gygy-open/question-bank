"""Composition 节点 AST 整体替换契约的聚焦测试。

覆盖:客户端 UUID 建树 + position 规范化、同 UUID 原地保留 + 删除缺席、陈旧 revision
409 且无部分变更、question 节点服务端钉 revision、跨 subject question 拒绝、
非 owner personal 404、非法节点 422、一次 replace 一条 nodes_replaced 事件,
以及 question_details module 的 answer_item 规范化(范围增删、题序、保留、anchor 混排)。
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


def _heading(text: str, level: int, nid: str | None = None) -> dict:
    return {
        "id": nid or _uid(), "node_kind": "block", "node_type": "heading",
        "content": _rich_doc(text), "props": {"level": level},
    }


def _page_break(nid: str | None = None) -> dict:
    return {"id": nid or _uid(), "node_kind": "block", "node_type": "page_break"}


def _answer_space(nid: str | None = None, *, lines: int = 3, style: str = "blank") -> dict:
    return {
        "id": nid or _uid(), "node_kind": "block", "node_type": "answer_space",
        "props": {"lines": lines, "style": style},
    }


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


def _answer_item(module_id: str, source_node_id: str, *, nid: str | None = None,
                 included: bool = True, overrides: dict | None = None) -> dict:
    complete_overrides = {
        "answer": None,
        "thinking": None,
        "analysis": None,
        "summary": None,
        **(overrides or {}),
    }
    return {
        "id": nid or _uid(), "parent_id": module_id, "slot": "body",
        "node_kind": "reference", "node_type": "answer_item",
        "source_question_node_id": source_node_id,
        "props": {"included": included, "overrides": complete_overrides},
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


async def _put_nodes(client, sid, comp_id, headers, *, expected_revision, nodes, scope="shared"):
    return await client.put(
        f"{API}/subjects/{sid}/compositions/{comp_id}/nodes?scope={scope}",
        json={"expected_revision": expected_revision, "nodes": nodes},
        headers=headers,
    )


def _roots(nodes: list) -> list:
    return sorted([n for n in nodes if n["parent_id"] is None], key=lambda n: n["position"])


def _children(nodes: list, parent_id: str) -> list:
    return sorted([n for n in nodes if n["parent_id"] == parent_id], key=lambda n: n["position"])


# --------------------------------------------------------------------------- #
# 建树:客户端 UUID + position 规范化
# --------------------------------------------------------------------------- #
async def test_replace_builds_tree_with_positions(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    n1, n2, n3 = _uid(), _uid(), _uid()
    r = await _put_nodes(
        client, sid, comp["id"], h,
        expected_revision=1,
        nodes=[_rich_text("第一段", n1), _heading("标题", 2, n2), _page_break(n3)],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["revision"] == 2
    roots = _roots(body["nodes"])
    assert [n["id"] for n in roots] == [n1, n2, n3]
    assert [n["position"] for n in roots] == [0, 1, 2]
    assert [n["node_type"] for n in roots] == ["rich_text", "heading", "page_break"]


async def test_replace_roundtrips_answer_space(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    a1 = _uid()
    r = await _put_nodes(
        client, sid, comp["id"], h,
        expected_revision=1,
        nodes=[_answer_space(a1, lines=6, style="lined")],
    )
    assert r.status_code == 200, r.text
    roots = _roots(r.json()["nodes"])
    assert [n["node_type"] for n in roots] == ["answer_space"]
    assert roots[0]["props"] == {"lines": 6, "style": "lined"}


# --------------------------------------------------------------------------- #
# 同 UUID 原地保留 + 删除缺席
# --------------------------------------------------------------------------- #
async def test_replace_keeps_uuid_and_deletes_absent(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    a, b = _uid(), _uid()
    first = await _put_nodes(
        client, sid, comp["id"], h,
        expected_revision=1, nodes=[_rich_text("A", a), _rich_text("B", b)],
    )
    assert first.status_code == 200

    second = await _put_nodes(
        client, sid, comp["id"], h,
        expected_revision=2,
        nodes=[{"id": a, "node_kind": "block", "node_type": "rich_text", "content": _rich_doc("A2")}],
    )
    assert second.status_code == 200, second.text
    roots = _roots(second.json()["nodes"])
    assert [n["id"] for n in roots] == [a]  # b 已删除
    assert roots[0]["content"] == _rich_doc("A2")

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h
    )
    assert [n["id"] for n in _roots(detail.json()["nodes"])] == [a]


# --------------------------------------------------------------------------- #
# 陈旧 revision → 409 且无部分变更
# --------------------------------------------------------------------------- #
async def test_stale_revision_conflicts_without_partial_change(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    a = _uid()
    ok = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_rich_text("A", a)])
    assert ok.status_code == 200

    stale = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,  # 已是 2
        nodes=[_rich_text("A", a), _rich_text("B")],
    )
    assert stale.status_code == 409, stale.text

    detail = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h
    )
    body = detail.json()
    assert body["revision"] == 2
    assert [n["id"] for n in _roots(body["nodes"])] == [a]


# --------------------------------------------------------------------------- #
# question 节点:服务端钉当前 revision + 冻结快照;跨 subject 拒绝
# --------------------------------------------------------------------------- #
async def test_question_node_pins_current_revision(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid, content_revision=7)

    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id)]
    )
    assert r.status_code == 200, r.text
    node = _roots(r.json()["nodes"])[0]
    assert node["question_id"] == q.id
    assert node["question_revision"] == 7
    assert node["content"]["q_type"] == "free_response"


async def test_question_node_cross_subject_rejected(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=ctx["subject2"].id, content_revision=1)

    r = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[_question(q.id)])
    assert r.status_code == 422, r.text


async def test_question_node_accepts_and_persists_number(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid, content_revision=1)

    node = {**_question(q.id), "props": {"number": "1.1"}}
    r = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[node])
    assert r.status_code == 200, r.text
    assert _roots(r.json()["nodes"])[0]["props"] == {"number": "1.1"}


@pytest.mark.parametrize(
    "bad_props",
    [
        {"number": 1},
        {"number": "x" * 17},
        {"label": "1"},
    ],
)
async def test_question_node_invalid_number_rejected(client, ctx, db_session, bad_props):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid, content_revision=1)

    node = {**_question(q.id), "props": bad_props}
    r = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[node])
    assert r.status_code == 422, r.text


async def test_question_node_accepts_show_overrides(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid, content_revision=1)

    node = {**_question(q.id), "props": {"show": {"answer": True, "analysis": False}}}
    r = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[node])
    assert r.status_code == 200, r.text
    assert _roots(r.json()["nodes"])[0]["props"] == {"show": {"answer": True, "analysis": False}}


async def test_question_node_accepts_and_persists_score(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid, content_revision=1)

    node = {**_question(q.id), "props": {"number": "1", "score": 2.5}}
    r = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[node])
    assert r.status_code == 200, r.text
    assert _roots(r.json()["nodes"])[0]["props"] == {"number": "1", "score": 2.5}


@pytest.mark.parametrize(
    "bad_score",
    [-1, 1001, "5", True],
)
async def test_question_node_invalid_score_rejected(client, ctx, db_session, bad_score):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid, content_revision=1)

    node = {**_question(q.id), "props": {"score": bad_score}}
    r = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[node])
    assert r.status_code == 422, r.text


@pytest.mark.parametrize(
    "bad_show",
    [
        {"answer": "yes"},
        {"unknown": True},
        "nope",
    ],
)
async def test_question_node_invalid_show_rejected(client, ctx, db_session, bad_show):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid, content_revision=1)

    node = {**_question(q.id), "props": {"show": bad_show}}
    r = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[node])
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# 非 owner personal → 404
# --------------------------------------------------------------------------- #
async def test_personal_composition_not_editable_by_others(client, ctx):
    sid = ctx["subject"].id
    owner = _auth(ctx["user"])
    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=personal",
        json={"title": "私有稿"}, headers=owner,
    )
    assert r.status_code == 201, r.text
    comp = r.json()

    intruder = _auth(ctx["other"])
    r = await _put_nodes(
        client, sid, comp["id"], intruder, expected_revision=1, nodes=[_rich_text("X")], scope="personal"
    )
    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# 非法节点 → 422 / 400
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_node",
    [
        {"id": _uid(), "node_kind": "block", "node_type": "heading", "content": None, "props": {"level": 1}},
        {"id": _uid(), "node_kind": "block", "node_type": "heading",
         "content": {"type": "doc", "content": [{"type": "paragraph"}, {"type": "paragraph"}]}, "props": {"level": 1}},
        {"id": _uid(), "node_kind": "block", "node_type": "heading",
         "content": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "x"}]}]}, "props": {"level": 5}},
        {"id": _uid(), "node_kind": "block", "node_type": "page_break", "content": {"type": "doc", "content": []}},
        {"id": _uid(), "node_kind": "block", "node_type": "rich_text", "content": {"type": "doc", "content": []}},
        {"id": "not-a-uuid", "node_kind": "block", "node_type": "page_break"},
        {"id": _uid(), "node_kind": "module", "node_type": "question_details", "props": {"scope": "nope", "fields": {}}},
        {"id": _uid(), "node_kind": "reference", "node_type": "answer_item", "source_question_node_id": _uid()},
    ],
)
async def test_invalid_nodes_rejected(client, ctx, bad_node):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    r = await _put_nodes(client, sid, comp["id"], h, expected_revision=1, nodes=[bad_node])
    assert r.status_code == 422, r.text


async def test_duplicate_node_ids_rejected(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    dup = _uid()
    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[_rich_text("A", dup), _rich_text("B", dup)],
    )
    assert r.status_code == 422, r.text


async def test_answer_item_wrong_parent_rejected(client, ctx, db_session):
    """answer_item 挂到非 module 节点 → 400(跨节点校验)。"""
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q = await _seed_question(db_session, subject_id=sid)

    qn = _uid()
    rich = _uid()
    ai = _answer_item(rich, qn)  # parent 指向一个 rich_text,不是 module
    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[_question(q.id, qn), _rich_text("正文", rich), ai],
    )
    assert r.status_code == 400, r.text


# --------------------------------------------------------------------------- #
# 一次 replace 一条 nodes_replaced 事件
# --------------------------------------------------------------------------- #
async def test_replace_writes_single_event(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)

    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/nodes?scope=shared",
        json={"expected_revision": 1, "batch_id": "batch-xyz", "nodes": [_rich_text("A")]},
        headers=h,
    )
    assert r.status_code == 200, r.text

    count = await db_session.scalar(
        select(func.count()).select_from(CompositionEvent).where(
            CompositionEvent.composition_id == comp["id"],
            CompositionEvent.event_type == "nodes_replaced",
        )
    )
    assert count == 1
    event = (
        await db_session.execute(
            select(CompositionEvent).where(
                CompositionEvent.composition_id == comp["id"],
                CompositionEvent.event_type == "nodes_replaced",
            )
        )
    ).scalars().first()
    assert event.batch_id == "batch-xyz"
    assert event.composition_revision == 2


# --------------------------------------------------------------------------- #
# question_details module:answer_item 按范围规范化 + 题序
# --------------------------------------------------------------------------- #
async def test_module_normalizes_answer_items_by_scope(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q1 = await _seed_question(db_session, subject_id=sid)
    q2 = await _seed_question(db_session, subject_id=sid)

    qn1, qn2, mod = _uid(), _uid(), _uid()
    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[_question(q1.id, qn1), _question(q2.id, qn2), _module("all", {"answer": True}, mod)],
    )
    assert r.status_code == 200, r.text
    children = _children(r.json()["nodes"], mod)
    assert [c["node_type"] for c in children] == ["answer_item", "answer_item"]
    assert [c["source_question_node_id"] for c in children] == [qn1, qn2]
    assert [c["position"] for c in children] == [0, 1]
    # 默认 props。
    assert children[0]["props"] == {"included": True, "overrides": {"answer": None, "thinking": None, "analysis": None, "summary": None}}


async def test_module_scope_before_limits_answer_items(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q1 = await _seed_question(db_session, subject_id=sid)
    q2 = await _seed_question(db_session, subject_id=sid)

    qn1, qn2, mod = _uid(), _uid(), _uid()
    # module 位于 q1 之后、q2 之前 → scope=before 只覆盖 q1。
    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[_question(q1.id, qn1), _module("before", {}, mod), _question(q2.id, qn2)],
    )
    assert r.status_code == 200, r.text
    children = _children(r.json()["nodes"], mod)
    assert [c["source_question_node_id"] for c in children] == [qn1]


async def test_module_preserves_included_and_overrides(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q1 = await _seed_question(db_session, subject_id=sid)

    qn1, mod, ai = _uid(), _uid(), _uid()
    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[
            _question(q1.id, qn1),
            _module("all", {"answer": True}, mod),
            _answer_item(mod, qn1, nid=ai, included=False, overrides={"answer": True}),
        ],
    )
    assert r.status_code == 200, r.text
    children = _children(r.json()["nodes"], mod)
    assert len(children) == 1
    assert children[0]["id"] == ai  # 保留客户端 UUID
    assert children[0]["props"]["included"] is False
    assert children[0]["props"]["overrides"]["answer"] is True


async def test_module_interleaves_custom_by_anchor(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q1 = await _seed_question(db_session, subject_id=sid)

    qn1, mod, ai, custom = _uid(), _uid(), _uid(), _uid()
    custom_heading = {
        "id": custom, "parent_id": mod, "slot": "body", "node_kind": "block",
        "node_type": "heading", "content": _rich_doc("答案区"), "props": {"level": 3},
        "anchor_before_node_id": ai,
    }
    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[
            _question(q1.id, qn1),
            _module("all", {}, mod),
            _answer_item(mod, qn1, nid=ai),
            custom_heading,
        ],
    )
    assert r.status_code == 200, r.text
    children = _children(r.json()["nodes"], mod)
    # 自定义标题锚定在 answer_item 之前。
    assert [c["id"] for c in children] == [custom, ai]
    assert [c["position"] for c in children] == [0, 1]


async def test_module_unanchored_custom_before_answer_items_leads(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q1 = await _seed_question(db_session, subject_id=sid)

    qn1, mod, title = _uid(), _uid(), _uid()
    # 无 anchor 的标题作为模块首个子节点 → 规范化后应置顶。
    title_heading = {
        "id": title, "parent_id": mod, "slot": "body", "node_kind": "block",
        "node_type": "heading", "content": _rich_doc("参考答案"), "props": {"level": 2},
    }
    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[
            _question(q1.id, qn1),
            _module("all", {}, mod),
            title_heading,
        ],
    )
    assert r.status_code == 200, r.text
    children = _children(r.json()["nodes"], mod)
    assert [c["node_type"] for c in children] == ["heading", "answer_item"]
    assert children[0]["id"] == title


async def test_duplicate_composition_clones_nodes_with_new_ids(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_shared_composition(client, sid, h)
    q1 = await _seed_question(db_session, subject_id=sid)

    qn1, mod, ai = _uid(), _uid(), _uid()
    r = await _put_nodes(
        client, sid, comp["id"], h, expected_revision=1,
        nodes=[
            _question(q1.id, qn1),
            _module("all", {"answer": True}, mod),
            _answer_item(mod, qn1, nid=ai, included=False, overrides={"answer": True}),
        ],
    )
    assert r.status_code == 200, r.text
    original_node_ids = {n["id"] for n in r.json()["nodes"]}
    revision_after_nodes = r.json()["revision"]

    # 题号开关一并克隆(而不仅仅是节点)。
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={"expected_revision": revision_after_nodes, "numbering_enabled": True},
        headers=h,
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/duplicate?scope=shared", headers=h,
    )
    assert r.status_code == 201, r.text
    dup = r.json()
    assert dup["id"] != comp["id"]
    assert dup["title"] == "稿件 副本"
    assert dup["numbering_enabled"] is True
    # revision=1(创建)+1(结算题号/赋分/显示字段设置)。
    assert dup["revision"] == 2

    got = await client.get(
        f"{API}/subjects/{sid}/compositions/{dup['id']}?scope=shared", headers=h,
    )
    assert got.status_code == 200
    dup_nodes = got.json()["nodes"]
    assert len(dup_nodes) == 3
    # 节点 id 全部重新生成,不与源稿件重复。
    assert original_node_ids.isdisjoint({n["id"] for n in dup_nodes})

    dup_question = next(n for n in dup_nodes if n["node_type"] == "question")
    assert dup_question["question_id"] == q1.id
    assert dup_question["question_revision"] == 1  # 原样搬运,不重新冻结

    dup_module = next(n for n in dup_nodes if n["node_type"] == "question_details")
    dup_answer_item = next(n for n in dup_nodes if n["node_type"] == "answer_item")
    assert dup_answer_item["parent_id"] == dup_module["id"]
    assert dup_answer_item["source_question_node_id"] == dup_question["id"]
    assert dup_answer_item["props"]["included"] is False
    assert dup_answer_item["props"]["overrides"]["answer"] is True

    # 源稿件不受影响。
    original = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h,
    )
    assert len(original.json()["nodes"]) == 3

