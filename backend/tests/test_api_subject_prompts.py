"""subject_prompts 端点的权限矩阵。

改造前这些端点要求超管;现在改为登录用户 + 学科作用域:
读用 VIEW_QUESTION,写/删用 MANAGE_SUBJECT。delete 也补齐学科存在性检查。
"""
import pytest

from app.core.security import create_access_token
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User

API = "/api/v1"
KEY = "AI_EXTRACT_PROMPT"


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
    admin = await _seed_user(db_session, username="sp_admin", is_superuser=True)
    math = await _seed_subject(db_session, name="数学", slug="sp-math")
    phys = await _seed_subject(db_session, name="物理", slug="sp-phys")
    viewer = await _seed_user(db_session, username="sp_viewer")
    editor = await _seed_user(db_session, username="sp_editor")
    manager = await _seed_user(db_session, username="sp_manager")
    outsider = await _seed_user(db_session, username="sp_outsider")
    await _grant(db_session, user=viewer, subject=math, role="viewer")
    await _grant(db_session, user=editor, subject=math, role="editor")
    await _grant(db_session, user=manager, subject=math, role="manager")
    return {
        "admin": admin, "math": math, "phys": phys,
        "viewer": viewer, "editor": editor, "manager": manager, "outsider": outsider,
    }


# --------------------------------------------------------------------------- #
# 读:VIEW_QUESTION
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("who", ["viewer", "editor", "manager", "admin"])
async def test_read_allowed_for_members_and_admin(client, ctx, who):
    r = await client.get(f"{API}/subjects/{ctx['math'].id}/prompts", headers=_auth(ctx[who]))
    assert r.status_code == 200, r.text
    keys = {item["key"] for item in r.json()}
    assert KEY in keys


async def test_read_forbidden_for_outsider(client, ctx):
    r = await client.get(f"{API}/subjects/{ctx['math'].id}/prompts", headers=_auth(ctx["outsider"]))
    assert r.status_code == 403, r.text


async def test_read_requires_auth(client, ctx):
    r = await client.get(f"{API}/subjects/{ctx['math'].id}/prompts")
    assert r.status_code == 401, r.text


# --------------------------------------------------------------------------- #
# 写:MANAGE_SUBJECT
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("who", ["manager", "admin"])
async def test_write_allowed_for_manager_and_admin(client, ctx, who):
    r = await client.put(
        f"{API}/subjects/{ctx['math'].id}/prompts/{KEY}",
        json={"value": "自定义提示词"},
        headers=_auth(ctx[who]),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value"] == "自定义提示词"
    assert body["is_custom"] is True


@pytest.mark.parametrize("who", ["viewer", "editor", "outsider"])
async def test_write_forbidden_below_manager(client, ctx, who):
    r = await client.put(
        f"{API}/subjects/{ctx['math'].id}/prompts/{KEY}",
        json={"value": "x"},
        headers=_auth(ctx[who]),
    )
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# 删:MANAGE_SUBJECT
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("who", ["manager", "admin"])
async def test_delete_allowed_for_manager_and_admin(client, ctx, who):
    r = await client.delete(
        f"{API}/subjects/{ctx['math'].id}/prompts/{KEY}", headers=_auth(ctx[who])
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_custom"] is False


@pytest.mark.parametrize("who", ["viewer", "editor", "outsider"])
async def test_delete_forbidden_below_manager(client, ctx, who):
    r = await client.delete(
        f"{API}/subjects/{ctx['math'].id}/prompts/{KEY}", headers=_auth(ctx[who])
    )
    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# 存在性 / 未知 key
# --------------------------------------------------------------------------- #
async def test_read_missing_subject_404(client, ctx):
    r = await client.get(f"{API}/subjects/999999/prompts", headers=_auth(ctx["admin"]))
    assert r.status_code == 404, r.text


async def test_write_missing_subject_404(client, ctx):
    r = await client.put(
        f"{API}/subjects/999999/prompts/{KEY}",
        json={"value": "x"},
        headers=_auth(ctx["admin"]),
    )
    assert r.status_code == 404, r.text


async def test_delete_missing_subject_404(client, ctx):
    r = await client.delete(f"{API}/subjects/999999/prompts/{KEY}", headers=_auth(ctx["admin"]))
    assert r.status_code == 404, r.text


async def test_write_unknown_key_404(client, ctx):
    r = await client.put(
        f"{API}/subjects/{ctx['math'].id}/prompts/NOPE",
        json={"value": "x"},
        headers=_auth(ctx["admin"]),
    )
    assert r.status_code == 404, r.text


async def test_delete_unknown_key_404(client, ctx):
    r = await client.delete(
        f"{API}/subjects/{ctx['math'].id}/prompts/NOPE", headers=_auth(ctx["admin"])
    )
    assert r.status_code == 404, r.text
