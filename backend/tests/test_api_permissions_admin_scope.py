"""学科/知识点/标签管理权限收紧的聚焦测试(承接 test_api_permissions.py 的口径)。

覆盖:
- 学科实体 create/update/delete 仅超管。
- 知识点/标签/标签分类:增删改需 MANAGE_SUBJECT(负责人),编辑/只读老师不可。
- 跨学科读知识点/标签被拒。
"""
import pytest

from app.core.security import create_access_token
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User

API = "/api/v1"


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


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


@pytest.fixture
async def ctx(db_session):
    admin = await _seed_user(db_session, username="admin2", is_superuser=True)
    math = await _seed_subject(db_session, name="数学", slug="math")
    phys = await _seed_subject(db_session, name="物理", slug="phys")
    editor = await _seed_user(db_session, username="m_editor")
    viewer = await _seed_user(db_session, username="m_viewer")
    manager = await _seed_user(db_session, username="m_manager")
    await _grant(db_session, user=editor, subject=math, role="editor")
    await _grant(db_session, user=viewer, subject=math, role="viewer")
    await _grant(db_session, user=manager, subject=math, role="manager")
    return {
        "admin": admin, "math": math, "phys": phys,
        "editor": editor, "viewer": viewer, "manager": manager,
    }


# --------------------------------------------------------------------------- #
# 学科实体仅超管
# --------------------------------------------------------------------------- #
async def test_subject_create_admin_only(client, ctx):
    payload = {"name": "化学", "slug": "chem"}
    r = await client.post(f"{API}/subjects", json=payload, headers=_auth(ctx["manager"]))
    assert r.status_code == 400, r.text  # get_current_active_superuser -> 400

    r = await client.post(f"{API}/subjects", json=payload, headers=_auth(ctx["admin"]))
    assert r.status_code == 200, r.text


async def test_subject_delete_admin_only(client, ctx):
    r = await client.delete(f"{API}/subjects/{ctx['math'].id}", headers=_auth(ctx["manager"]))
    assert r.status_code == 400, r.text


# --------------------------------------------------------------------------- #
# 知识点 / 标签 / 标签分类:增改需 MANAGE_SUBJECT
# --------------------------------------------------------------------------- #
async def test_knowledge_point_manage_requires_manager(client, ctx):
    sid = ctx["math"].id
    payload = {"name": "函数", "slug": "func", "subject_id": sid}

    r = await client.post(f"{API}/knowledge-points", json=payload, headers=_auth(ctx["editor"]))
    assert r.status_code == 403, r.text
    r = await client.post(f"{API}/knowledge-points", json=payload, headers=_auth(ctx["manager"]))
    assert r.status_code == 200, r.text


async def test_tag_manage_requires_manager(client, ctx):
    sid = ctx["math"].id
    payload = {"name": "易错", "subject_id": sid}

    r = await client.post(f"{API}/tags", json=payload, headers=_auth(ctx["editor"]))
    assert r.status_code == 403, r.text
    r = await client.post(f"{API}/tags", json=payload, headers=_auth(ctx["manager"]))
    assert r.status_code == 200, r.text


async def test_tag_category_manage_requires_manager(client, ctx):
    sid = ctx["math"].id
    payload = {"name": "题型", "subject_id": sid}

    r = await client.post(f"{API}/tag-categories", json=payload, headers=_auth(ctx["editor"]))
    assert r.status_code == 403, r.text
    r = await client.post(f"{API}/tag-categories", json=payload, headers=_auth(ctx["manager"]))
    assert r.status_code == 200, r.text


# --------------------------------------------------------------------------- #
# 跨学科读被拒
# --------------------------------------------------------------------------- #
async def test_cross_subject_read_forbidden(client, ctx):
    phys = ctx["phys"].id
    # editor 只属于数学,读物理的标签/知识点应 403。
    r = await client.get(f"{API}/tags?subject_id={phys}", headers=_auth(ctx["editor"]))
    assert r.status_code == 403, r.text
    r = await client.get(f"{API}/knowledge-points?subject_id={phys}", headers=_auth(ctx["editor"]))
    assert r.status_code == 403, r.text
    # 自己学科可读。
    r = await client.get(f"{API}/tags?subject_id={ctx['math'].id}", headers=_auth(ctx["editor"]))
    assert r.status_code == 200, r.text
