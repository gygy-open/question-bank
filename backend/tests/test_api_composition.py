"""Folder / Composition 元数据 CRUD API 的聚焦测试(第二阶段)。

覆盖:shared 可读写、personal 隔离、客户端不能指定 owner、跨 subject 不可见、
父目录范围不一致、自引用/祖先环、非空目录删除 409、组稿 folder 一致性、
组稿乐观锁冲突与自增、事件与业务变更同事务。
"""
import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.composition import CompositionEvent
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


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


@pytest.fixture
async def ctx(db_session):
    user = await _seed_user(db_session, username="alice")
    other = await _seed_user(db_session, username="bob")
    subject = await _seed_subject(db_session)
    subject2 = await _seed_subject(db_session, name="物理", slug="phys")
    return {
        "user": user,
        "other": other,
        "subject": subject,
        "subject2": subject2,
    }


# --------------------------------------------------------------------------- #
# shared 基本流程
# --------------------------------------------------------------------------- #
async def test_shared_folder_and_composition_flow(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    r = await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared", json={"name": "共享目录"}, headers=h
    )
    assert r.status_code == 201, r.text
    folder = r.json()
    assert folder["owner_id"] is None
    assert folder["scope_type"] == "shared"

    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared",
        json={"title": "稿件A", "folder_id": folder["id"]},
        headers=h,
    )
    assert r.status_code == 201, r.text
    comp = r.json()
    assert comp["owner_id"] is None
    assert comp["revision"] == 1
    assert comp["folder_id"] == folder["id"]

    # 另一个已认证用户也能读到 shared 内容。
    r = await client.get(
        f"{API}/subjects/{sid}/compositions?scope=shared", headers=_auth(ctx["other"])
    )
    assert r.status_code == 200
    assert len(r.json()) == 1


async def test_composition_list_can_filter_root_only(client, ctx):
    sid = ctx["subject"].id
    headers = _auth(ctx["user"])

    folder_response = await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared",
        json={"name": "子目录"},
        headers=headers,
    )
    folder_id = folder_response.json()["id"]
    for payload in (
        {"title": "根目录组稿"},
        {"title": "子目录组稿", "folder_id": folder_id},
    ):
        response = await client.post(
            f"{API}/subjects/{sid}/compositions?scope=shared",
            json=payload,
            headers=headers,
        )
        assert response.status_code == 201, response.text

    response = await client.get(
        f"{API}/subjects/{sid}/compositions?scope=shared&root_only=true",
        headers=headers,
    )
    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["根目录组稿"]


async def test_composition_list_can_filter_by_keyword(client, ctx):
    sid = ctx["subject"].id
    headers = _auth(ctx["user"])

    for title in ("期中数学试卷", "期末数学试卷", "英语听力材料"):
        response = await client.post(
            f"{API}/subjects/{sid}/compositions?scope=shared",
            json={"title": title},
            headers=headers,
        )
        assert response.status_code == 201, response.text

    response = await client.get(
        f"{API}/subjects/{sid}/compositions?scope=shared&keyword=数学",
        headers=headers,
    )
    assert response.status_code == 200
    assert {item["title"] for item in response.json()} == {"期中数学试卷", "期末数学试卷"}

    # 大小写不敏感。
    response = await client.get(
        f"{API}/subjects/{sid}/compositions?scope=shared&keyword=英语",
        headers=headers,
    )
    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["英语听力材料"]


# --------------------------------------------------------------------------- #
# personal 隔离
# --------------------------------------------------------------------------- #
async def test_personal_isolation(client, ctx):
    sid = ctx["subject"].id

    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=personal",
        json={"title": "我的稿"},
        headers=_auth(ctx["user"]),
    )
    assert r.status_code == 201
    comp = r.json()
    assert comp["owner_id"] == ctx["user"].id

    # 其他用户的 personal 列表看不到,get 也 404。
    r = await client.get(
        f"{API}/subjects/{sid}/compositions?scope=personal", headers=_auth(ctx["other"])
    )
    assert r.status_code == 200
    assert r.json() == []

    r = await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=personal",
        headers=_auth(ctx["other"]),
    )
    assert r.status_code == 404


async def test_client_cannot_specify_owner(client, ctx):
    sid = ctx["subject"].id

    # 即便请求体塞入 owner_id,shared 仍持久化 NULL,personal 仍强制当前用户。
    r = await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared",
        json={"name": "x", "owner_id": 9999},
        headers=_auth(ctx["user"]),
    )
    assert r.status_code == 201
    assert r.json()["owner_id"] is None

    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=personal",
        json={"title": "y", "owner_id": 9999},
        headers=_auth(ctx["user"]),
    )
    assert r.status_code == 201
    assert r.json()["owner_id"] == ctx["user"].id


async def test_cross_subject_not_visible(client, ctx):
    sid = ctx["subject"].id
    sid2 = ctx["subject2"].id
    h = _auth(ctx["user"])

    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "s1"}, headers=h
    )
    comp_id = r.json()["id"]

    r = await client.get(
        f"{API}/subjects/{sid2}/compositions/{comp_id}?scope=shared", headers=h
    )
    assert r.status_code == 404

    r = await client.get(f"{API}/subjects/{sid2}/compositions?scope=shared", headers=h)
    assert r.json() == []


# --------------------------------------------------------------------------- #
# Folder 结构不变量
# --------------------------------------------------------------------------- #
async def test_parent_folder_scope_mismatch(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    r = await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared", json={"name": "共享父"}, headers=h
    )
    shared_folder = r.json()["id"]

    # personal 目录以 shared 目录为父 → 父在 personal 范围内不可见 → 404。
    r = await client.post(
        f"{API}/subjects/{sid}/folders?scope=personal",
        json={"name": "私有子", "parent_id": shared_folder},
        headers=h,
    )
    assert r.status_code == 404


async def test_self_parent_rejected(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    r = await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared", json={"name": "f"}, headers=h
    )
    fid = r.json()["id"]

    r = await client.patch(
        f"{API}/subjects/{sid}/folders/{fid}?scope=shared",
        json={"parent_id": fid},
        headers=h,
    )
    assert r.status_code == 400


async def test_cycle_detection(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    a = (await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared", json={"name": "A"}, headers=h
    )).json()["id"]
    b = (await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared", json={"name": "B", "parent_id": a},
        headers=h,
    )).json()["id"]

    # 把 A 移到其子孙 B 之下 → 成环 → 400。
    r = await client.patch(
        f"{API}/subjects/{sid}/folders/{a}?scope=shared", json={"parent_id": b}, headers=h
    )
    assert r.status_code == 400


async def test_delete_nonempty_folder_conflict(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    folder = (await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared", json={"name": "非空"}, headers=h
    )).json()["id"]
    await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared",
        json={"title": "在里面", "folder_id": folder},
        headers=h,
    )

    r = await client.delete(f"{API}/subjects/{sid}/folders/{folder}?scope=shared", headers=h)
    assert r.status_code == 409


async def test_delete_empty_folder_ok(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])
    folder = (await client.post(
        f"{API}/subjects/{sid}/folders?scope=shared", json={"name": "空"}, headers=h
    )).json()["id"]

    r = await client.delete(f"{API}/subjects/{sid}/folders/{folder}?scope=shared", headers=h)
    assert r.status_code == 204

    r = await client.get(f"{API}/subjects/{sid}/folders?scope=shared", headers=h)
    assert all(f["id"] != folder for f in r.json())


async def test_composition_folder_consistency(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    # personal 目录,shared 组稿引用它 → 目录在 shared 范围不可见 → 404。
    personal_folder = (await client.post(
        f"{API}/subjects/{sid}/folders?scope=personal", json={"name": "私有"}, headers=h
    )).json()["id"]

    r = await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared",
        json={"title": "错目录", "folder_id": personal_folder},
        headers=h,
    )
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# 乐观锁与时间线
# --------------------------------------------------------------------------- #
async def test_revision_conflict_and_bump(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    comp = (await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "锁"}, headers=h
    )).json()
    assert comp["revision"] == 1

    # 陈旧 expected_revision → 409。
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={"expected_revision": 99, "title": "改"},
        headers=h,
    )
    assert r.status_code == 409

    # 正确 expected_revision → 成功且 revision+1。
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={"expected_revision": 1, "title": "新标题"},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["revision"] == 2
    assert r.json()["title"] == "新标题"


async def test_numbering_enabled_defaults_false_and_toggles(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    comp = (await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "题号"}, headers=h
    )).json()
    assert comp["numbering_enabled"] is False

    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={"expected_revision": 1, "numbering_enabled": True},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["numbering_enabled"] is True
    assert r.json()["revision"] == 2

    got = (await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h
    )).json()
    assert got["numbering_enabled"] is True


async def test_scoring_enabled_requires_numbering_and_cascades_off(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    comp = (await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "赋分"}, headers=h
    )).json()
    assert comp["scoring_enabled"] is False

    # 题号未开启时开启赋分 → 400。
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={"expected_revision": 1, "scoring_enabled": True},
        headers=h,
    )
    assert r.status_code == 400

    # 同一请求内一并开启题号与赋分 → 成功。
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={"expected_revision": 1, "numbering_enabled": True, "scoring_enabled": True},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["numbering_enabled"] is True
    assert r.json()["scoring_enabled"] is True

    # 仅关闭题号(未显式提及赋分) → 赋分级联关闭。
    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={"expected_revision": 2, "numbering_enabled": False},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["numbering_enabled"] is False
    assert r.json()["scoring_enabled"] is False



    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    comp = (await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "显示"}, headers=h
    )).json()
    assert comp["question_display"] == {
        "answer": False, "thinking": False, "analysis": False, "summary": False,
    }

    r = await client.patch(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared",
        json={"expected_revision": 1, "question_display": {"answer": True, "analysis": True}},
        headers=h,
    )
    assert r.status_code == 200, r.text
    # 部分 map 被补全为四字段。
    assert r.json()["question_display"] == {
        "answer": True, "thinking": False, "analysis": True, "summary": False,
    }

    got = (await client.get(
        f"{API}/subjects/{sid}/compositions/{comp['id']}?scope=shared", headers=h
    )).json()
    assert got["question_display"]["answer"] is True
    assert got["question_display"]["analysis"] is True


async def test_delete_restore_with_revision(client, ctx):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    comp = (await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "回收"}, headers=h
    )).json()
    cid = comp["id"]

    r = await client.delete(
        f"{API}/subjects/{sid}/compositions/{cid}?scope=shared&expected_revision=1", headers=h
    )
    assert r.status_code == 204

    # 默认列表看不到,回收站(only_deleted)可见。
    r = await client.get(f"{API}/subjects/{sid}/compositions?scope=shared", headers=h)
    assert all(c["id"] != cid for c in r.json())
    r = await client.get(
        f"{API}/subjects/{sid}/compositions?scope=shared&only_deleted=true", headers=h
    )
    assert any(c["id"] == cid for c in r.json())

    # 还原需带正确 revision(删除已使其 +1 → 2)。
    r = await client.post(
        f"{API}/subjects/{sid}/compositions/{cid}/restore?scope=shared&expected_revision=2",
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["deleted_at"] is None
    assert r.json()["revision"] == 3


async def test_events_written_same_transaction(client, ctx, db_session):
    sid = ctx["subject"].id
    h = _auth(ctx["user"])

    comp = (await client.post(
        f"{API}/subjects/{sid}/compositions?scope=shared", json={"title": "事件"}, headers=h
    )).json()
    cid = comp["id"]

    await client.patch(
        f"{API}/subjects/{sid}/compositions/{cid}?scope=shared",
        json={"expected_revision": 1, "title": "改"},
        headers=h,
    )
    await client.delete(
        f"{API}/subjects/{sid}/compositions/{cid}?scope=shared&expected_revision=2", headers=h
    )

    rows = (await db_session.execute(
        select(CompositionEvent).where(CompositionEvent.composition_id == cid)
        .order_by(CompositionEvent.id)
    )).scalars().all()
    types = [e.event_type for e in rows]
    assert types == ["created", "updated", "deleted"]
    # 事件记录变更后的 revision 与 actor。
    assert rows[0].composition_revision == 1
    assert rows[1].composition_revision == 2
    assert rows[2].composition_revision == 3
    assert all(e.actor_id == ctx["user"].id for e in rows)
