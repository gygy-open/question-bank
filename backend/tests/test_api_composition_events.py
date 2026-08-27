"""Composition 时间线 (/events) 契约测试。

覆盖:按 id 倒序、游标翻页(limit + before_id)不重不漏、actor 嵌套信息、
跨 scope/subject 404、软删除稿仍可查看时间线。
"""
import uuid

import pytest

from app.core.security import create_access_token
from app.models.subject import Subject
from app.models.user import User

API = "/api/v1"


def _uid() -> str:
    return str(uuid.uuid4())


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


async def _update(client, sid, comp_id, headers, *, expected_revision, scope="shared"):
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp_id}?scope={scope}",
        json={"expected_revision": expected_revision, "title": "改名"},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _list_events(client, sid, comp_id, headers, *, scope="shared", before_id=None, limit=None):
    params = f"?scope={scope}"
    if before_id is not None:
        params += f"&before_id={before_id}"
    if limit is not None:
        params += f"&limit={limit}"
    return await client.get(f"{API}/subjects/{sid}/compositions/{comp_id}/events{params}", headers=headers)


# --------------------------------------------------------------------------- #
# 基本顺序 + actor 嵌套
# --------------------------------------------------------------------------- #
async def test_events_ordered_desc_with_actor(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    await _update(client, sid, comp["id"], h, expected_revision=1)

    r = await _list_events(client, sid, comp["id"], h)
    assert r.status_code == 200, r.text
    page = r.json()
    assert page["has_more"] is False
    types = [e["event_type"] for e in page["items"]]
    assert types == ["updated", "created"]
    assert page["items"][0]["actor"]["username"] == "alice"
    assert page["items"][0]["actor_id"] == ctx["user"].id


# --------------------------------------------------------------------------- #
# 游标翻页:limit=1 逐页翻完,不重不漏
# --------------------------------------------------------------------------- #
async def test_events_cursor_pagination(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)
    for rev in range(1, 4):
        await _update(client, sid, comp["id"], h, expected_revision=rev)

    seen_ids = []
    before_id = None
    for _ in range(10):
        r = await _list_events(client, sid, comp["id"], h, before_id=before_id, limit=1)
        assert r.status_code == 200, r.text
        page = r.json()
        assert len(page["items"]) == 1
        seen_ids.append(page["items"][0]["id"])
        if not page["has_more"]:
            break
        before_id = page["items"][-1]["id"]
    else:
        pytest.fail("did not terminate pagination")

    assert len(seen_ids) == len(set(seen_ids)) == 4
    assert seen_ids == sorted(seen_ids, reverse=True)


# --------------------------------------------------------------------------- #
# 跨 scope / subject → 404;软删除稿仍可查看时间线
# --------------------------------------------------------------------------- #
async def test_events_cross_scope_subject_not_found(client, ctx):
    sid = ctx["subject"].id
    sid2 = ctx["subject2"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)

    r = await _list_events(client, sid, comp["id"], h, scope="personal")
    assert r.status_code == 404
    r = await _list_events(client, sid2, comp["id"], h)
    assert r.status_code == 404


async def test_events_visible_after_soft_delete(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    comp = await _create_composition(client, sid, h)

    r = await client.delete(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared&expected_revision=1",
        headers=h,
    )
    assert r.status_code == 204, r.text

    r = await _list_events(client, sid, comp["id"], h)
    assert r.status_code == 200, r.text
    types = [e["event_type"] for e in r.json()["items"]]
    assert types == ["deleted", "created"]
