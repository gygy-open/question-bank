"""权限方案 v1 的聚焦测试:学科隔离 + 题目私有 + 成员管理 + 能力真源。

覆盖:
- 学科作用域角色 viewer/editor/manager 的写权限。
- 跨学科不可见 / 不可写。
- 私有题:创建者与超管可见,其他人看不到。
- 私有题禁止加入共享组稿(允许加入个人组稿)。
- 学科成员管理(仅 MANAGE_MEMBERS 可操作)。
- /users/me/permissions 单一真源。
"""
import json

import pytest

from app.core.security import create_access_token
from app.models.question import Question, QuestionType, QuestionVisibility
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User

API = "/api/v1"

_DOC = json.dumps({"type": "doc", "content": [{"type": "paragraph"}]})


async def _seed_user(db_session, *, username, is_superuser=False) -> User:
    user = User(
        username=username, full_name=username, hashed_password="x",
        is_active=True, is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _seed_subject(db_session, *, name, slug) -> Subject:
    subject = Subject(name=name, slug=slug)
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)
    return subject


async def _grant(db_session, *, user, subject, role) -> None:
    db_session.add(SubjectMember(user_id=user.id, subject_id=subject.id, role=role))
    await db_session.commit()


async def _seed_question(
    db_session, *, subject, created_by, visibility=QuestionVisibility.PUBLIC.value
) -> Question:
    q = Question(
        content=_DOC,
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=subject.id,
        created_by=created_by.id,
        visibility=visibility,
    )
    db_session.add(q)
    await db_session.commit()
    await db_session.refresh(q)
    return q


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


def _min_question_payload(subject_id: int, visibility="public") -> dict:
    return {
        "content": {"type": "doc", "content": [{"type": "paragraph"}]},
        "q_type": "free_response",
        "subject_id": subject_id,
        "visibility": visibility,
    }


@pytest.fixture
async def ctx(db_session):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)
    math = await _seed_subject(db_session, name="数学", slug="math")
    phys = await _seed_subject(db_session, name="物理", slug="phys")
    editor = await _seed_user(db_session, username="math_editor")
    viewer = await _seed_user(db_session, username="math_viewer")
    manager = await _seed_user(db_session, username="math_manager")
    outsider = await _seed_user(db_session, username="outsider")
    await _grant(db_session, user=editor, subject=math, role="editor")
    await _grant(db_session, user=viewer, subject=math, role="viewer")
    await _grant(db_session, user=manager, subject=math, role="manager")
    return {
        "admin": admin, "math": math, "phys": phys,
        "editor": editor, "viewer": viewer, "manager": manager, "outsider": outsider,
    }


# --------------------------------------------------------------------------- #
# 学科作用域写权限
# --------------------------------------------------------------------------- #
async def test_editor_can_create_viewer_cannot(client, ctx):
    r = await client.post(
        f"{API}/questions", json=_min_question_payload(ctx["math"].id),
        headers=_auth(ctx["editor"]),
    )
    assert r.status_code == 200, r.text

    r = await client.post(
        f"{API}/questions", json=_min_question_payload(ctx["math"].id),
        headers=_auth(ctx["viewer"]),
    )
    assert r.status_code == 403, r.text


async def test_editor_cannot_write_other_subject(client, ctx):
    r = await client.post(
        f"{API}/questions", json=_min_question_payload(ctx["phys"].id),
        headers=_auth(ctx["editor"]),
    )
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# 跨学科不可见 + 私有题
# --------------------------------------------------------------------------- #
async def test_list_scoped_to_subject_and_visibility(client, ctx, db_session):
    # admin 在物理建题(editor 无权访问物理)。
    await _seed_question(db_session, subject=ctx["phys"], created_by=ctx["admin"])
    # 数学公开题。
    await _seed_question(db_session, subject=ctx["math"], created_by=ctx["editor"])
    # 别人(manager)在数学建的私有题。
    await _seed_question(
        db_session, subject=ctx["math"], created_by=ctx["manager"],
        visibility=QuestionVisibility.PRIVATE.value,
    )

    r = await client.get(f"{API}/questions?size=50", headers=_auth(ctx["editor"]))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    # 只应看到数学的那道公开题:物理题被学科隔离,别人的私有题被隐藏。
    subject_ids = {it["subject_id"] for it in items}
    assert subject_ids == {ctx["math"].id}
    assert all(it["visibility"] == "public" for it in items)
    assert len(items) == 1


async def test_private_question_visibility(client, ctx, db_session):
    priv = await _seed_question(
        db_session, subject=ctx["math"], created_by=ctx["editor"],
        visibility=QuestionVisibility.PRIVATE.value,
    )
    # 创建者可见。
    r = await client.get(f"{API}/questions/{priv.id}", headers=_auth(ctx["editor"]))
    assert r.status_code == 200
    # 同学科他人不可见(404,避免泄漏存在性)。
    r = await client.get(f"{API}/questions/{priv.id}", headers=_auth(ctx["viewer"]))
    assert r.status_code == 404
    # 超管可见。
    r = await client.get(f"{API}/questions/{priv.id}", headers=_auth(ctx["admin"]))
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# 私有题禁止进共享组稿
# --------------------------------------------------------------------------- #
async def test_private_question_rejected_in_shared_composition(client, ctx, db_session):
    sid = ctx["math"].id
    priv = await _seed_question(
        db_session, subject=ctx["math"], created_by=ctx["admin"],
        visibility=QuestionVisibility.PRIVATE.value,
    )
    # 建共享组稿。
    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared",
        json={"title": "共享稿"}, headers=_auth(ctx["admin"]),
    )
    assert r.status_code == 201, r.text
    comp = r.json()

    node = {
        "id": "11111111-1111-4111-8111-111111111111",
        "node_kind": "block",
        "node_type": "question",
        "parent_id": None,
        "slot": None,
        "position": 0,
        "question_id": priv.id,
        "props": {},
    }
    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{comp['id']}/nodes",
        json={"expected_revision": comp["revision"], "nodes": [node]},
        headers=_auth(ctx["admin"]),
    )
    assert r.status_code == 422, r.text


# --------------------------------------------------------------------------- #
# 成员管理
# --------------------------------------------------------------------------- #
async def test_member_management_requires_manage(client, ctx):
    sid = ctx["math"].id
    # editor(非 manager)不能管理成员。
    r = await client.get(f"{API}/subjects/{sid}/members", headers=_auth(ctx["editor"]))
    assert r.status_code == 403
    # manager 可以。
    r = await client.get(f"{API}/subjects/{sid}/members", headers=_auth(ctx["manager"]))
    assert r.status_code == 200
    # manager 给 outsider 授予 editor。
    r = await client.put(
        f"{API}/subjects/{sid}/members/{ctx['outsider'].id}",
        json={"role": "editor"}, headers=_auth(ctx["manager"]),
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "editor"
    # 非法角色被拒。
    r = await client.put(
        f"{API}/subjects/{sid}/members/{ctx['outsider'].id}",
        json={"role": "god"}, headers=_auth(ctx["manager"]),
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# 学科列表隔离 + 能力真源
# --------------------------------------------------------------------------- #
async def test_subject_list_scoped(client, ctx):
    r = await client.get(f"{API}/subjects", headers=_auth(ctx["editor"]))
    assert r.status_code == 200
    ids = {s["id"] for s in r.json()}
    assert ids == {ctx["math"].id}

    r = await client.get(f"{API}/subjects", headers=_auth(ctx["admin"]))
    assert {ctx["math"].id, ctx["phys"].id}.issubset({s["id"] for s in r.json()})


async def test_me_permissions_source_of_truth(client, ctx):
    r = await client.get(f"{API}/users/me/permissions", headers=_auth(ctx["editor"]))
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["is_superuser"] is False
    assert data["accessible_subject_ids"] == [ctx["math"].id]
    caps = data["capabilities"][str(ctx["math"].id)]
    assert "edit_question" in caps
    assert "manage_members" not in caps

    r = await client.get(f"{API}/users/me/permissions", headers=_auth(ctx["admin"]))
    assert r.json()["accessible_subject_ids"] is None
