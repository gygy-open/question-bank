"""组稿域门禁的聚焦测试。

组稿此前只校验登录:任何用户都能读写任意学科的 shared 稿件。现在读路径要 VIEW_QUESTION、
写路径要 EDIT_QUESTION,均按学科作用域判定。

覆盖:读写权限矩阵、非成员被拒、personal 稿也要求成员身份、跨学科仍是 404 而非 403。
"""
import pytest
from sqlalchemy import select

from app.core.permissions import SubjectRole
from app.core.security import create_access_token
from app.models.composition import Composition, ScopeType
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


async def _seed_subject(db_session, *, name="数学", slug="math") -> Subject:
    subject = Subject(name=name, slug=slug)
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)
    return subject


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


@pytest.fixture
async def ctx(db_session, grant_role):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)
    viewer = await _seed_user(db_session, username="viewer")
    editor = await _seed_user(db_session, username="editor")
    manager = await _seed_user(db_session, username="manager")
    outsider = await _seed_user(db_session, username="outsider")

    subject = await _seed_subject(db_session)
    subject2 = await _seed_subject(db_session, name="物理", slug="phys")

    await grant_role(viewer, subject, SubjectRole.VIEWER)
    await grant_role(editor, subject, SubjectRole.EDITOR)
    await grant_role(manager, subject, SubjectRole.MANAGER)

    # 由 editor 建一份 shared 稿件作为读写目标。
    comp = Composition(
        title="期中卷",
        subject_id=subject.id,
        scope_type=ScopeType.SHARED,
        owner_id=None,
        created_by=editor.id,
        revision=1,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)

    return {
        "admin": admin, "viewer": viewer, "editor": editor, "manager": manager,
        "outsider": outsider, "subject": subject, "subject2": subject2, "comp": comp,
    }


# --------------------------------------------------------------------------- #
# 读路径 —— VIEW_QUESTION
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "actor, expected",
    [("viewer", 200), ("editor", 200), ("manager", 200), ("admin", 200), ("outsider", 403)],
)
async def test_list_compositions_permission_matrix(client, ctx, actor, expected):
    r = await client.get(
        f"{API}/subjects/{ctx['subject'].id}/compositions?scope=shared",
        headers=_auth(ctx[actor]),
    )
    assert r.status_code == expected


@pytest.mark.parametrize(
    "actor, expected",
    [("viewer", 200), ("editor", 200), ("manager", 200), ("admin", 200), ("outsider", 403)],
)
async def test_list_folders_permission_matrix(client, ctx, actor, expected):
    r = await client.get(
        f"{API}/subjects/{ctx['subject'].id}/folders?scope=shared",
        headers=_auth(ctx[actor]),
    )
    assert r.status_code == expected


@pytest.mark.parametrize(
    "path_suffix",
    ["", "/question-revisions", "/question-group-revisions", "/versions", "/events"],
)
async def test_composition_reads_reject_non_member(client, ctx, path_suffix):
    """稿件维度的读路径全部要成员身份,不能靠任一入口绕过。"""
    sid, cid = ctx["subject"].id, ctx["comp"].id
    r = await client.get(
        f"{API}/subjects/{sid}/compositions/{cid}{path_suffix}?scope=shared",
        headers=_auth(ctx["outsider"]),
    )
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
# 写路径 —— EDIT_QUESTION
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "actor, expected",
    [("editor", 201), ("manager", 201), ("admin", 201), ("viewer", 403), ("outsider", 403)],
)
async def test_create_composition_permission_matrix(client, ctx, actor, expected):
    r = await client.post(
        f"{API}/subjects/{ctx['subject'].id}/compositions?scope=shared",
        json={"title": "新稿"},
        headers=_auth(ctx[actor]),
    )
    assert r.status_code == expected


@pytest.mark.parametrize(
    "actor, expected",
    [("editor", 201), ("manager", 201), ("admin", 201), ("viewer", 403), ("outsider", 403)],
)
async def test_create_folder_permission_matrix(client, ctx, actor, expected):
    r = await client.post(
        f"{API}/subjects/{ctx['subject'].id}/folders?scope=shared",
        json={"name": "目录"},
        headers=_auth(ctx[actor]),
    )
    assert r.status_code == expected


@pytest.mark.parametrize(
    "actor, expected",
    [("editor", 200), ("manager", 200), ("admin", 200), ("viewer", 403), ("outsider", 403)],
)
async def test_update_composition_permission_matrix(client, ctx, actor, expected):
    sid, cid = ctx["subject"].id, ctx["comp"].id
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{cid}?scope=shared",
        json={"expected_revision": 1, "title": "改名"},
        headers=_auth(ctx[actor]),
    )
    assert r.status_code == expected


@pytest.mark.parametrize(
    "actor, expected",
    [("editor", 200), ("manager", 200), ("admin", 200), ("viewer", 403), ("outsider", 403)],
)
async def test_replace_nodes_permission_matrix(client, ctx, actor, expected):
    sid, cid = ctx["subject"].id, ctx["comp"].id
    r = await client.put(
        f"{API}/subjects/{sid}/compositions/{cid}/nodes?scope=shared",
        json={"expected_revision": 1, "nodes": []},
        headers=_auth(ctx[actor]),
    )
    assert r.status_code == expected


# --------------------------------------------------------------------------- #
# 边界:personal 稿 / 跨学科
# --------------------------------------------------------------------------- #
async def test_personal_composition_still_requires_membership(client, ctx, db_session):
    """自己拥有的 personal 稿也要学科成员身份 —— owner_id 只决定可见性,不决定权限。"""
    comp = Composition(
        title="我的草稿",
        subject_id=ctx["subject"].id,
        scope_type=ScopeType.PERSONAL,
        owner_id=ctx["outsider"].id,
        created_by=ctx["outsider"].id,
        revision=1,
    )
    db_session.add(comp)
    await db_session.commit()
    await db_session.refresh(comp)

    sid = ctx["subject"].id
    h = _auth(ctx["outsider"])
    r = await client.get(f"{API}/subjects/{sid}/compositions/{comp.id}?scope=personal", headers=h)
    assert r.status_code == 403
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp.id}?scope=personal",
        json={"expected_revision": 1, "title": "x"}, headers=h,
    )
    assert r.status_code == 403


async def test_member_cross_subject_is_404_not_403(client, ctx, grant_role):
    """已是两个学科的成员时,跨学科定位仍必须是 404,不能被门禁抢先变成 403。"""
    await grant_role(ctx["editor"], ctx["subject2"], SubjectRole.EDITOR)
    sid2, cid = ctx["subject2"].id, ctx["comp"].id
    r = await client.get(
        f"{API}/subjects/{sid2}/compositions/{cid}?scope=shared", headers=_auth(ctx["editor"])
    )
    assert r.status_code == 404


async def test_unknown_subject_is_404_before_403(client, ctx):
    """学科不存在时先 404,与 capability 层 load→authorize 的顺序一致。"""
    r = await client.get(
        f"{API}/subjects/999999/compositions?scope=shared", headers=_auth(ctx["outsider"])
    )
    assert r.status_code == 404


async def test_revoked_member_loses_write_access(client, ctx, db_session):
    """撤销成员关系后立即失去写权限(权限来自 subject_memberships,无缓存)。"""
    sid = ctx["subject"].id
    h = _auth(ctx["editor"])
    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "a"}, headers=h
    )
    assert r.status_code == 201

    member = (
        await db_session.execute(
            select(SubjectMember).where(
                SubjectMember.user_id == ctx["editor"].id,
                SubjectMember.subject_id == sid,
            )
        )
    ).scalar_one()
    await db_session.delete(member)
    await db_session.commit()

    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "b"}, headers=h
    )
    assert r.status_code == 403
