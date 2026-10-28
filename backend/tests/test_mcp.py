"""MCP 接入:API Key 生命周期、/api/mcp 鉴权、工具清单与调用。"""
import asyncio
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import capabilities
from app.core.security import create_access_token, hash_api_key
from app.crud.crud_api_key import LAST_USED_THROTTLE, api_key as crud_api_key
from app.mcp_server.tools import (
    CAPABILITY_OUTPUT_TYPES,
    EXCLUDED_CAPABILITIES,
    all_tools,
    tool_name_for,
)
from app.models.activity_log import ActivityLog
from app.models.api_key import ApiKey
from app.models.composition import Composition
from app.models.question import Question
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User
from app.services.mcp_settings import set_mcp_enabled

API = "/api/v1"
MCP = "/api/mcp"
_ACCEPT = "application/json, text/event-stream"


async def _seed_user(db, *, username, is_superuser=False, is_active=True) -> User:
    user = User(
        username=username, full_name=username, hashed_password="x",
        is_active=is_active, is_superuser=is_superuser,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _seed_subject(db, *, name, slug) -> Subject:
    subject = Subject(name=name, slug=slug)
    db.add(subject)
    await db.commit()
    await db.refresh(subject)
    return subject


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest_asyncio.fixture
async def mcp_client(client, engine, monkeypatch):
    """REST + MCP 客户端:MCP 中间件/工具直连 sessionmaker,需指向测试引擎;会话管理器需在 lifespan 里跑。"""
    from app.db import session as db_session
    from app.mcp_server import run_mcp

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: maker)

    # anyio 的 cancel scope 必须在同一 task 里进出,而 fixture 的 setup/teardown 不在同一 task
    started, stop = asyncio.Event(), asyncio.Event()

    async def _runner():
        async with run_mcp():
            started.set()
            await stop.wait()

    task = asyncio.create_task(_runner())
    await started.wait()
    yield client
    stop.set()
    await task


@pytest_asyncio.fixture
async def ctx(db_session):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)
    alice = await _seed_user(db_session, username="alice")
    bob = await _seed_user(db_session, username="bob")
    math = await _seed_subject(db_session, name="数学", slug="math")
    phys = await _seed_subject(db_session, name="物理", slug="phys")
    db_session.add(SubjectMember(user_id=alice.id, subject_id=math.id, role="editor"))
    db_session.add(SubjectMember(user_id=bob.id, subject_id=math.id, role="viewer"))
    await db_session.commit()
    return {"admin": admin, "alice": alice, "bob": bob, "math": math, "phys": phys}


async def _create_key(client, user: User, name: str = "k") -> str:
    resp = await client.post(f"{API}/api-keys", json={"name": name}, headers=_auth(user))
    assert resp.status_code == 201, resp.text
    return resp.json()["key"]


async def _rpc(client, key: str | None, method: str, params: dict | None = None, *, headers=None):
    h = {"Accept": _ACCEPT}
    if key is not None:
        h["Authorization"] = f"Bearer {key}"
    h.update(headers or {})
    return await client.post(
        MCP,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers=h,
    )


async def _call(client, key: str, name: str, arguments: dict) -> dict:
    resp = await _rpc(client, key, "tools/call", {"name": name, "arguments": arguments})
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


# --------------------------------------------------------------------------- #
# API Key 生命周期
# --------------------------------------------------------------------------- #
async def test_create_key_returns_plaintext_once(mcp_client, db_session, ctx):
    resp = await mcp_client.post(f"{API}/api-keys", json={"name": " 我的 Claude "}, headers=_auth(ctx["alice"]))
    assert resp.status_code == 201
    body = resp.json()
    assert body["key"].startswith("qb_")
    assert body["name"] == "我的 Claude"
    assert body["key"].startswith(body["prefix"])

    row = (await db_session.execute(select(ApiKey))).scalars().one()
    assert row.key_hash == hash_api_key(body["key"])
    assert body["key"] not in (row.prefix, row.key_hash)

    listed = (await mcp_client.get(f"{API}/api-keys", headers=_auth(ctx["alice"]))).json()
    assert [k["id"] for k in listed] == [body["id"]]
    assert "key" not in listed[0]

    # 别人的列表里看不到
    assert (await mcp_client.get(f"{API}/api-keys", headers=_auth(ctx["bob"]))).json() == []


async def test_blank_name_rejected(mcp_client, ctx):
    resp = await mcp_client.post(f"{API}/api-keys", json={"name": "   "}, headers=_auth(ctx["alice"]))
    assert resp.status_code == 422


async def test_key_limit(mcp_client, ctx, monkeypatch):
    from app.api.v1.endpoints import api_keys as endpoint

    monkeypatch.setattr(endpoint, "MAX_KEYS_PER_USER", 2)
    await _create_key(mcp_client, ctx["alice"])
    await _create_key(mcp_client, ctx["alice"])
    resp = await mcp_client.post(f"{API}/api-keys", json={"name": "x"}, headers=_auth(ctx["alice"]))
    assert resp.status_code == 400
    assert resp.json()["code"] == "api_key.limit_reached"
    assert resp.json()["params"] == {"limit": 2}


async def test_revoke_own_key_only(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    key_id = (await mcp_client.get(f"{API}/api-keys", headers=_auth(ctx["alice"]))).json()[0]["id"]

    resp = await mcp_client.delete(f"{API}/api-keys/{key_id}", headers=_auth(ctx["bob"]))
    assert resp.status_code == 404
    assert resp.json()["code"] == "api_key.not_found"

    assert (await _rpc(mcp_client, key, "tools/list")).status_code == 200
    resp = await mcp_client.delete(f"{API}/api-keys/{key_id}", headers=_auth(ctx["alice"]))
    assert resp.status_code == 204
    # 撤销立即生效
    assert (await _rpc(mcp_client, key, "tools/list")).status_code == 401


async def test_admin_lists_and_revokes_all_keys(mcp_client, ctx):
    await _create_key(mcp_client, ctx["alice"], "a")
    await _create_key(mcp_client, ctx["bob"], "b")

    assert (await mcp_client.get(f"{API}/api-keys/all", headers=_auth(ctx["alice"]))).status_code == 400

    rows = (await mcp_client.get(f"{API}/api-keys/all", headers=_auth(ctx["admin"]))).json()
    assert {r["username"] for r in rows} == {"alice", "bob"}
    assert all("key" not in r for r in rows)

    bob_key = next(r for r in rows if r["username"] == "bob")
    resp = await mcp_client.delete(f"{API}/api-keys/all/{bob_key['id']}", headers=_auth(ctx["admin"]))
    assert resp.status_code == 204
    rows = (await mcp_client.get(f"{API}/api-keys/all", headers=_auth(ctx["admin"]))).json()
    assert [r["username"] for r in rows] == ["alice"]


async def test_api_key_cannot_call_rest(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    resp = await mcp_client.get(f"{API}/api-keys", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 403


async def test_deleting_user_removes_keys(mcp_client, db_session, ctx):
    await _create_key(mcp_client, ctx["bob"])
    await db_session.delete(ctx["bob"])
    await db_session.commit()
    assert (await db_session.execute(select(ApiKey))).scalars().all() == []


async def test_touch_is_throttled(db_session, ctx):
    from app.schemas.api_key import ApiKeyCreate

    row, _ = await crud_api_key.create_for_user(db_session, user_id=ctx["alice"].id, obj_in=ApiKeyCreate(name="k"))
    t0 = datetime(2026, 1, 1, 12, 0, 0)
    await crud_api_key.touch(db_session, api_key=row, now=t0)
    await crud_api_key.touch(db_session, api_key=row, now=t0 + timedelta(seconds=5))
    assert row.last_used_at == t0
    await crud_api_key.touch(db_session, api_key=row, now=t0 + LAST_USED_THROTTLE)
    assert row.last_used_at == t0 + LAST_USED_THROTTLE


# --------------------------------------------------------------------------- #
# MCP 开关 / 信息
# --------------------------------------------------------------------------- #
async def test_mcp_info_and_toggle(mcp_client, ctx):
    info = (await mcp_client.get(f"{API}/api-keys/mcp-info", headers=_auth(ctx["alice"]))).json()
    assert info == {"enabled": True, "path": MCP}

    resp = await mcp_client.put(f"{API}/api-keys/mcp-settings", json={"enabled": False}, headers=_auth(ctx["alice"]))
    assert resp.status_code == 400

    resp = await mcp_client.put(f"{API}/api-keys/mcp-settings", json={"enabled": False}, headers=_auth(ctx["admin"]))
    assert resp.json()["enabled"] is False
    info = (await mcp_client.get(f"{API}/api-keys/mcp-info", headers=_auth(ctx["alice"]))).json()
    assert info["enabled"] is False

    # 开关不出现在通用设置列表里,也不能经通用设置 API 修改
    settings = (await mcp_client.get(f"{API}/settings", headers=_auth(ctx["admin"]))).json()
    assert all(not s["key"].startswith("mcp.") for s in settings)
    resp = await mcp_client.put(f"{API}/settings/mcp.enabled", json={"value": "true"}, headers=_auth(ctx["admin"]))
    assert resp.status_code == 403


# --------------------------------------------------------------------------- #
# /api/mcp 鉴权
# --------------------------------------------------------------------------- #
async def test_mcp_requires_api_key(mcp_client, ctx):
    resp = await _rpc(mcp_client, None, "tools/list")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Bearer")

    assert (await _rpc(mcp_client, "qb_not-a-real-key", "tools/list")).status_code == 401
    # 登录 JWT 不能当 MCP 凭证
    jwt = create_access_token(ctx["alice"].id)
    assert (await _rpc(mcp_client, jwt, "tools/list")).status_code == 401


async def test_mcp_rejects_inactive_user(mcp_client, db_session, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    ctx["alice"].is_active = False
    await db_session.commit()
    resp = await _rpc(mcp_client, key, "tools/list")
    assert resp.status_code == 403
    assert resp.json()["code"] == "auth.inactive_user"


async def test_mcp_disabled(mcp_client, db_session, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    await set_mcp_enabled(db_session, False)
    resp = await _rpc(mcp_client, key, "tools/list")
    assert resp.status_code == 403
    assert resp.json()["code"] == "mcp.disabled"


async def test_mcp_origin_check(mcp_client, ctx, monkeypatch):
    key = await _create_key(mcp_client, ctx["alice"])
    evil = await _rpc(mcp_client, key, "tools/list", headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    same = await _rpc(mcp_client, key, "tools/list", headers={"Origin": "http://test"})
    assert same.status_code == 200

    monkeypatch.setenv("MCP_ALLOWED_ORIGINS", "https://evil.example")
    assert (await _rpc(mcp_client, key, "tools/list", headers={"Origin": "https://evil.example"})).status_code == 200


async def test_trailing_slash_path(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    resp = await mcp_client.post(
        MCP + "/",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers={"Authorization": f"Bearer {key}", "Accept": _ACCEPT},
    )
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# 工具清单
# --------------------------------------------------------------------------- #
def test_every_exposed_capability_has_output_type():
    exposed = {c.name for c in capabilities.all_capabilities()} - EXCLUDED_CAPABILITIES
    assert set(CAPABILITY_OUTPUT_TYPES) == exposed


def test_composition_tools_hide_owner_and_provided_flags():
    tools = all_tools()
    for tool in tools.values():
        props = tool.input_schema.get("properties", {})
        assert "owner_id" not in props or tool.capability is None or not tool.capability.startswith("composition.")
        assert not any(p.endswith("_provided") for p in props), tool.name


async def test_tools_list(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    resp = await _rpc(mcp_client, key, "tools/list")
    assert resp.status_code == 200
    tools = {t["name"]: t for t in resp.json()["result"]["tools"]}

    exposed = {c.name for c in capabilities.all_capabilities()} - EXCLUDED_CAPABILITIES
    for name in exposed:
        assert tool_name_for(name) in tools
    for excluded in EXCLUDED_CAPABILITIES:
        assert tool_name_for(excluded) not in tools
    assert {"list_subjects", "search_questions", "get_question", "get_composition"} <= set(tools)

    assert tools["question_delete"]["annotations"]["destructiveHint"] is True
    assert tools["list_subjects"]["annotations"]["readOnlyHint"] is True
    assert tools["question_create"]["annotations"]["readOnlyHint"] is False


# --------------------------------------------------------------------------- #
# 工具调用
# --------------------------------------------------------------------------- #
async def test_list_subjects_respects_membership(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    result = await _call(mcp_client, key, "list_subjects", {})
    assert [s["name"] for s in result["structuredContent"]["items"]] == ["数学"]

    admin_key = await _create_key(mcp_client, ctx["admin"])
    result = await _call(mcp_client, admin_key, "list_subjects", {})
    assert {s["name"] for s in result["structuredContent"]["items"]} == {"数学", "物理"}


async def test_question_create_and_audit(mcp_client, db_session, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    result = await _call(mcp_client, key, "question_create", {
        "content": {"type": "doc", "content": [{"type": "paragraph"}]},
        "q_type": "free_response",
        "subject_id": ctx["math"].id,
    })
    assert result["isError"] is False, result
    qid = result["structuredContent"]["id"]
    question = await db_session.get(Question, qid)
    assert question.created_by == ctx["alice"].id
    assert question.status == "draft"

    logs = (await db_session.execute(
        select(ActivityLog).where(ActivityLog.action == "mcp_call")
    )).scalars().all()
    assert len(logs) == 1
    assert logs[0].user_id == ctx["alice"].id
    assert logs[0].details["tool"] == "question_create"
    assert logs[0].details["ok"] is True

    # 读工具能拿回来
    got = await _call(mcp_client, key, "get_question", {"id": qid})
    assert got["structuredContent"]["id"] == qid
    found = await _call(mcp_client, key, "search_questions", {"subject_id": ctx["math"].id})
    assert [q["id"] for q in found["structuredContent"]["items"]] == [qid]


async def test_permissions_are_inherited(mcp_client, db_session, ctx):
    bob_key = await _create_key(mcp_client, ctx["bob"])  # math viewer
    result = await _call(mcp_client, bob_key, "question_create", {
        "content": {"type": "doc", "content": [{"type": "paragraph"}]},
        "q_type": "free_response",
        "subject_id": ctx["math"].id,
    })
    assert result["isError"] is True
    assert '"status": 403' in result["content"][0]["text"]

    # 失败的写尝试也要审计
    logs = (await db_session.execute(
        select(ActivityLog).where(ActivityLog.action == "mcp_call")
    )).scalars().all()
    assert [log.details["ok"] for log in logs] == [False]

    # 非成员学科的读也被拒
    result = await _call(mcp_client, bob_key, "list_tags", {"subject_id": ctx["phys"].id})
    assert result["isError"] is True
    assert "auth.forbidden" in result["content"][0]["text"]


async def test_validation_error_is_reported(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    result = await _call(mcp_client, key, "question_create", {"subject_id": ctx["math"].id})
    assert result["isError"] is True
    assert "validation.failed" in result["content"][0]["text"]


async def test_unknown_tool(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    result = await _call(mcp_client, key, "nope", {})
    assert result["isError"] is True


async def test_search_rejects_unknown_q_type(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    result = await _call(mcp_client, key, "search_questions", {"subject_id": ctx["math"].id, "q_type": "bogus"})
    assert result["isError"] is True
    assert '"status": 422' in result["content"][0]["text"]


async def test_personal_composition_owner_is_forced(mcp_client, db_session, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    result = await _call(mcp_client, key, "composition_create", {
        "subject_id": ctx["math"].id,
        "scope_type": "personal",
        "owner_id": ctx["bob"].id,  # 企图伪造归属,应被忽略
        "title": "我的卷子",
    })
    assert result["isError"] is False, result
    comp = await db_session.get(Composition, result["structuredContent"]["id"])
    assert comp.owner_id == ctx["alice"].id

    # 列表/详情也只看得到自己的个人稿
    listed = await _call(mcp_client, key, "list_compositions", {"subject_id": ctx["math"].id, "scope_type": "personal"})
    assert [c["id"] for c in listed["structuredContent"]["items"]] == [comp.id]
    detail = await _call(mcp_client, key, "get_composition", {
        "subject_id": ctx["math"].id, "scope_type": "personal", "composition_id": comp.id,
    })
    revision = detail["structuredContent"]["revision"]

    # folder_id_provided 由参数形态推出:没传 folder_id 就不动目录
    updated = await _call(mcp_client, key, "composition_update", {
        "subject_id": ctx["math"].id, "scope_type": "personal", "composition_id": comp.id,
        "expected_revision": revision, "title": "改名",
    })
    assert updated["isError"] is False, updated
    assert updated["structuredContent"]["title"] == "改名"

    bad = await _call(mcp_client, key, "composition_update", {
        "subject_id": ctx["math"].id, "scope_type": "personal", "composition_id": comp.id,
        "expected_revision": updated["structuredContent"]["revision"], "status_value": "bogus",
    })
    assert bad["isError"] is True


async def test_shared_composition_is_shared(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    result = await _call(mcp_client, key, "composition_create", {
        "subject_id": ctx["math"].id, "scope_type": "shared", "title": "共享卷",
    })
    assert result["isError"] is False, result
    bob_key = await _create_key(mcp_client, ctx["bob"])
    listed = await _call(mcp_client, bob_key, "list_compositions", {"subject_id": ctx["math"].id, "scope_type": "shared"})
    assert [c["title"] for c in listed["structuredContent"]["items"]] == ["共享卷"]


def test_model_facing_text_is_english():
    """工具描述/参数 schema/服务说明是给模型看的,统一英文,不随界面语言翻译。"""
    import json
    import re

    from app.mcp_server.server import INSTRUCTIONS

    cjk = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")
    assert not cjk.search(INSTRUCTIONS)
    for tool in all_tools().values():
        blob = tool.description + json.dumps(tool.input_schema, ensure_ascii=False)
        found = cjk.findall(blob)
        assert not found, f"{tool.name} has non-English model-facing text"


# --------------------------------------------------------------------------- #
# 媒体上传(预签名 URL)
# --------------------------------------------------------------------------- #
def _png_bytes() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8, 6), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


async def _upload_url(client, key: str, subject_id: int) -> dict:
    result = await _call(client, key, "create_media_upload_url", {"subject_id": subject_id})
    assert result["isError"] is False, result
    return result["structuredContent"]


def _path(url: str) -> str:
    from urllib.parse import urlsplit

    return urlsplit(url).path


async def test_media_upload_flow(mcp_client, db_session, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    info = await _upload_url(mcp_client, key, ctx["math"].id)
    assert info["upload_url"].startswith("http://test/api/mcp/uploads/")
    assert info["method"] == "POST" and info["form_field"] == "file"

    # 上传不需要 Authorization 头,令牌在 URL 里
    resp = await mcp_client.post(_path(info["upload_url"]), files={"file": ("plot.png", _png_bytes(), "image/png")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "image" and body["width"] == 8
    node = body["node"]
    assert node == {"type": "image", "attrs": {"src": f"/api/v1/media/{body['asset_id']}/content", "assetId": body["asset_id"]}}

    # 返回的节点能直接用于建题,且登记了媒体引用
    created = await _call(mcp_client, key, "question_create", {
        "content": {"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "见散点图"}]},
            node,
        ]},
        "q_type": "free_response",
        "subject_id": ctx["math"].id,
    })
    assert created["isError"] is False, created

    from app.models.media_asset import MediaReference

    refs = (await db_session.execute(
        select(MediaReference).where(MediaReference.asset_id == body["asset_id"])
    )).scalars().all()
    assert [r.owner_id for r in refs] == [created["structuredContent"]["id"]]

    logs = (await db_session.execute(select(ActivityLog).where(ActivityLog.action == "mcp_call"))).scalars().all()
    assert {log.details["tool"] for log in logs} >= {"create_media_upload_url", "media_upload", "question_create"}


async def test_media_upload_respects_base_url_headers(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    resp = await _rpc(mcp_client, key, "tools/call", {"name": "create_media_upload_url", "arguments": {"subject_id": ctx["math"].id}},
                      headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "qb.example.com"})
    url = resp.json()["result"]["structuredContent"]["upload_url"]
    assert url.startswith("https://qb.example.com/api/mcp/uploads/")


async def test_media_upload_requires_edit_permission(mcp_client, db_session, ctx):
    bob_key = await _create_key(mcp_client, ctx["bob"])  # viewer
    result = await _call(mcp_client, bob_key, "create_media_upload_url", {"subject_id": ctx["math"].id})
    assert result["isError"] is True
    assert "auth.forbidden" in result["content"][0]["text"]

    # 签发后被降权:上传时重新判权
    alice_key = await _create_key(mcp_client, ctx["alice"])
    info = await _upload_url(mcp_client, alice_key, ctx["math"].id)
    member = (await db_session.execute(
        select(SubjectMember).where(SubjectMember.user_id == ctx["alice"].id)
    )).scalars().one()
    member.role = "viewer"
    await db_session.commit()
    resp = await mcp_client.post(_path(info["upload_url"]), files={"file": ("a.png", _png_bytes(), "image/png")})
    assert resp.status_code == 403


async def test_media_upload_token_invalidated_by_revoke(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    info = await _upload_url(mcp_client, key, ctx["math"].id)
    key_id = (await mcp_client.get(f"{API}/api-keys", headers=_auth(ctx["alice"]))).json()[0]["id"]
    await mcp_client.delete(f"{API}/api-keys/{key_id}", headers=_auth(ctx["alice"]))
    resp = await mcp_client.post(_path(info["upload_url"]), files={"file": ("a.png", _png_bytes(), "image/png")})
    assert resp.status_code == 401


async def test_media_upload_token_expiry_and_isolation(mcp_client, ctx):
    from app.mcp_server.uploads import UPLOAD_TTL, create_upload_token

    key = await _create_key(mcp_client, ctx["alice"])
    key_id = (await mcp_client.get(f"{API}/api-keys", headers=_auth(ctx["alice"]))).json()[0]["id"]
    expired, _ = create_upload_token(
        user_id=ctx["alice"].id, key_id=key_id, subject_id=ctx["math"].id,
        now=datetime.now().astimezone() - UPLOAD_TTL - timedelta(seconds=5),
    )
    resp = await mcp_client.post(f"{MCP}/uploads/{expired}", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert resp.status_code == 401

    # 登录 JWT 不能当上传令牌,上传令牌也不能当登录 JWT
    login = create_access_token(ctx["alice"].id)
    resp = await mcp_client.post(f"{MCP}/uploads/{login}", files={"file": ("a.png", _png_bytes(), "image/png")})
    assert resp.status_code == 401
    upload, _ = create_upload_token(user_id=ctx["alice"].id, key_id=key_id, subject_id=ctx["math"].id)
    resp = await mcp_client.get(f"{API}/api-keys", headers={"Authorization": f"Bearer {upload}"})
    assert resp.status_code == 403


async def test_media_upload_rejects_non_media(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    info = await _upload_url(mcp_client, key, ctx["math"].id)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    resp = await mcp_client.post(_path(info["upload_url"]), files={"file": ("x.svg", svg, "image/svg+xml")})
    assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# 知识点 / 标签
# --------------------------------------------------------------------------- #
async def test_create_knowledge_point_and_tag(mcp_client, db_session, ctx):
    from app.models.knowledge_point import KnowledgePoint
    from app.models.tag import Tag
    from app.models.tag_category import TagCategory

    db_session.add(SubjectMember(user_id=ctx["admin"].id, subject_id=ctx["phys"].id, role="manager"))
    manager = await _seed_user(db_session, username="carol")
    db_session.add(SubjectMember(user_id=manager.id, subject_id=ctx["math"].id, role="manager"))
    category = TagCategory(name="年份", subject_id=ctx["math"].id)
    other_category = TagCategory(name="年份", subject_id=ctx["phys"].id)
    db_session.add_all([category, other_category])
    await db_session.commit()
    key = await _create_key(mcp_client, manager)
    math_id = ctx["math"].id

    parent = await _call(mcp_client, key, "knowledge_point_create", {"subject_id": math_id, "name": " 函数 "})
    assert parent["isError"] is False, parent
    assert parent["structuredContent"]["name"] == "函数"
    assert parent["structuredContent"]["slug"]  # 自动生成

    child = await _call(mcp_client, key, "knowledge_point_create", {
        "subject_id": math_id, "name": "一次函数", "parent_id": parent["structuredContent"]["id"],
    })
    assert child["structuredContent"]["parent_id"] == parent["structuredContent"]["id"]

    # 同名自动 slug 不冲突;显式重复 slug 报错
    again = await _call(mcp_client, key, "knowledge_point_create", {"subject_id": math_id, "name": "函数"})
    assert again["isError"] is False
    assert again["structuredContent"]["slug"] != parent["structuredContent"]["slug"]
    dup = await _call(mcp_client, key, "knowledge_point_create", {
        "subject_id": math_id, "name": "x", "slug": parent["structuredContent"]["slug"],
    })
    assert dup["isError"] is True and "knowledge_point.slug_exists" in dup["content"][0]["text"]

    # 父节点必须在同一学科
    phys_kp = KnowledgePoint(name="力", slug="li", subject_id=ctx["phys"].id)
    db_session.add(phys_kp)
    await db_session.commit()
    cross = await _call(mcp_client, key, "knowledge_point_create", {
        "subject_id": math_id, "name": "y", "parent_id": phys_kp.id,
    })
    assert cross["isError"] is True and "knowledge_point.not_found" in cross["content"][0]["text"]

    tag = await _call(mcp_client, key, "tag_create", {"subject_id": math_id, "name": "2024", "category_id": category.id})
    assert tag["isError"] is False, tag
    assert tag["structuredContent"]["category_id"] == category.id
    dup_tag = await _call(mcp_client, key, "tag_create", {"subject_id": math_id, "name": "2024"})
    assert dup_tag["isError"] is True and "tag.name_exists" in dup_tag["content"][0]["text"]
    cross_cat = await _call(mcp_client, key, "tag_create", {"subject_id": math_id, "name": "2025", "category_id": other_category.id})
    assert cross_cat["isError"] is True and "tag_category.not_found" in cross_cat["content"][0]["text"]

    listed = await _call(mcp_client, key, "list_tags", {"subject_id": math_id})
    assert [t["name"] for t in listed["structuredContent"]["items"]] == ["2024"]
    assert (await db_session.execute(select(Tag))).scalars().all()[0].created_by == manager.id


async def test_create_knowledge_point_and_tag_as_editor(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])  # editor
    kp = await _call(mcp_client, key, "knowledge_point_create", {"subject_id": ctx["math"].id, "name": "集合"})
    assert kp["isError"] is False, kp
    tag = await _call(mcp_client, key, "tag_create", {"subject_id": ctx["math"].id, "name": "基础"})
    assert tag["isError"] is False, tag


async def test_create_knowledge_point_requires_editor(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["bob"])  # viewer
    for tool, args in (
        ("knowledge_point_create", {"subject_id": ctx["math"].id, "name": "x"}),
        ("tag_create", {"subject_id": ctx["math"].id, "name": "x"}),
    ):
        result = await _call(mcp_client, key, tool, args)
        assert result["isError"] is True
        assert "auth.forbidden" in result["content"][0]["text"]


# --------------------------------------------------------------------------- #
# 组稿:高层写入
# --------------------------------------------------------------------------- #
async def _new_question(client, key, subject_id, text):
    r = await _call(client, key, "question_create", {
        "content": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]},
        "q_type": "free_response",
        "subject_id": subject_id,
    })
    assert r["isError"] is False, r
    return r["structuredContent"]["id"]


async def test_composition_write_nodes(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    sid = ctx["math"].id
    q1 = await _new_question(mcp_client, key, sid, "1+1=?")
    q2 = await _new_question(mcp_client, key, sid, "2+2=?")
    q3 = await _new_question(mcp_client, key, sid, "3+3=?")

    comp = (await _call(mcp_client, key, "composition_create", {"subject_id": sid, "scope_type": "personal", "title": "周测"}))["structuredContent"]
    base = {"subject_id": sid, "scope_type": "personal", "composition_id": comp["id"]}

    first = await _call(mcp_client, key, "composition_write_nodes", {**base, "expected_revision": comp["revision"], "nodes": [
        {"type": "heading", "text": "一、计算题", "level": 2},
        {"type": "rich_text", "markdown": "每题 5 分。\n\n计算 $a+b$。"},
        {"type": "question", "question_id": q1, "score": 5},
        {"type": "question", "question_id": q2, "score": 5},
        {"type": "question_details"},
    ]})
    assert first["isError"] is False, first
    assert first["structuredContent"]["added_nodes"] == 6  # Markdown 两段拆成两个节点

    detail = (await _call(mcp_client, key, "get_composition", {**base}))["structuredContent"]
    roots = [n for n in detail["nodes"] if n["parent_id"] is None]
    assert [n["node_type"] for n in roots] == ["heading", "rich_text", "rich_text", "question", "question", "question_details"]
    old_q_ids = {n["id"] for n in roots if n["node_type"] == "question"}
    answer_items = [n for n in detail["nodes"] if n["node_type"] == "answer_item"]
    assert len(answer_items) == 2  # 服务端按模块范围派生

    # append:原节点 id 保留,新题接在末尾,答案模块随之更新
    appended = await _call(mcp_client, key, "composition_write_nodes", {
        **base, "expected_revision": detail["revision"],
        "nodes": [{"type": "page_break"}, {"type": "question", "question_id": q3}],
    })
    assert appended["isError"] is False, appended
    detail2 = (await _call(mcp_client, key, "get_composition", {**base}))["structuredContent"]
    roots2 = sorted([n for n in detail2["nodes"] if n["parent_id"] is None], key=lambda n: n["position"])
    assert [n["node_type"] for n in roots2][-2:] == ["page_break", "question"]
    assert old_q_ids <= {n["id"] for n in roots2}
    assert len([n for n in detail2["nodes"] if n["node_type"] == "answer_item"]) == 3

    # 过期 revision 冲突
    stale = await _call(mcp_client, key, "composition_write_nodes", {**base, "expected_revision": detail["revision"], "nodes": [{"type": "page_break"}]})
    assert stale["isError"] is True and '"status": 409' in stale["content"][0]["text"]

    # replace:清掉原内容
    replaced = await _call(mcp_client, key, "composition_write_nodes", {
        **base, "expected_revision": detail2["revision"], "mode": "replace",
        "nodes": [{"type": "heading", "text": "重写"}],
    })
    assert replaced["structuredContent"]["total_nodes"] == 1


async def test_composition_write_nodes_validation(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    sid = ctx["math"].id
    comp = (await _call(mcp_client, key, "composition_create", {"subject_id": sid, "scope_type": "shared", "title": "x"}))["structuredContent"]
    base = {"subject_id": sid, "scope_type": "shared", "composition_id": comp["id"], "expected_revision": comp["revision"]}

    bad = await _call(mcp_client, key, "composition_write_nodes", {**base, "nodes": [{"type": "bogus"}]})
    assert bad["isError"] is True and "nodes[0].type" in bad["content"][0]["text"]
    missing = await _call(mcp_client, key, "composition_write_nodes", {**base, "nodes": [{"type": "question"}]})
    assert missing["isError"] is True and "question_id" in missing["content"][0]["text"]

    # 他人的个人稿不可见
    bob_key = await _create_key(mcp_client, ctx["bob"])
    personal = (await _call(mcp_client, key, "composition_create", {"subject_id": sid, "scope_type": "personal", "title": "mine"}))["structuredContent"]
    other = await _call(mcp_client, bob_key, "composition_write_nodes", {
        "subject_id": sid, "scope_type": "personal", "composition_id": personal["id"],
        "expected_revision": personal["revision"], "nodes": [{"type": "page_break"}],
    })
    assert other["isError"] is True


# --------------------------------------------------------------------------- #
# 查重
# --------------------------------------------------------------------------- #
async def test_mcp_duplicate_flow(mcp_client, ctx):
    key = await _create_key(mcp_client, ctx["alice"])
    sid = ctx["math"].id
    stem = "在三角形 ABC 中，已知角 A 等于六十度，边 BC 的长度为二，求三角形面积的最大值。"
    first = await _new_question(mcp_client, key, sid, stem)

    check = await _call(mcp_client, key, "check_question_duplicates", {
        "subject_id": sid, "q_type": "free_response",
        "content": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "1. " + stem}]}]},
    })
    assert [c["question_id"] for c in check["structuredContent"]["candidates"]] == [first]

    args = {
        "content": {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": stem}]}]},
        "q_type": "free_response", "subject_id": sid,
    }
    blocked = await _call(mcp_client, key, "question_create", args)
    assert blocked["isError"] is True
    text = blocked["content"][0]["text"]
    assert "question.duplicate_suspected" in text and f'"question_id": {first}' in text
    allowed = await _call(mcp_client, key, "question_create", {**args, "allow_duplicate": True})
    assert allowed["isError"] is False
