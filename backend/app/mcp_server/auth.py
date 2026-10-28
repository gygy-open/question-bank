"""MCP 入口的 ASGI 鉴权中间件。

顺序:Origin 校验 → MCP 总开关 → Bearer API Key → 用户有效性。通过后把调用者身份写进
`scope["qb.mcp_auth"]`,工具 handler 经 `ctx.request.scope` 取用。

为什么不用 SDK 的 Host 白名单:桌面版端口/局域网 IP 会变、Docker 域名由部署方决定,
白名单难以零配置;而每个请求都必须携带 API Key,浏览器侧的 DNS rebinding 拿不到 Key。
剩下的风险是「浏览器带着 Key 跨站调用」,用 Origin 校验挡住:带 Origin 的请求必须同源,
或在 `MCP_ALLOWED_ORIGINS` 里显式放行。原生 MCP 客户端不发 Origin,不受影响。
"""
from __future__ import annotations

import json
import os
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.security import looks_like_api_key
from app.crud.crud_api_key import api_key as crud_api_key
from app.crud.crud_user import user as crud_user
from app.db import session as db_session
from app.services.mcp_settings import is_mcp_enabled

SCOPE_KEY = "qb.mcp_auth"


@dataclass(frozen=True)
class McpAuth:
    user_id: int
    key_id: int
    key_prefix: str
    # 客户端看到的站点根地址(经反向代理时取 X-Forwarded-*),用于生成可回访的 URL
    base_url: str = ""


# 当前 MCP 调用的身份;由 server.execute_tool 设置,供需要 Key / 地址信息的工具读取。
current_auth: ContextVar[Optional[McpAuth]] = ContextVar("qb_mcp_auth", default=None)


def public_base_url(scope: Scope) -> str:
    proto = (_header(scope, b"x-forwarded-proto") or "").split(",")[0].strip() or scope.get("scheme", "http")
    host = (_header(scope, b"x-forwarded-host") or "").split(",")[0].strip() or _header(scope, b"host") or ""
    return f"{proto}://{host}" if host else ""


def _allowed_origins() -> set[str]:
    raw = os.getenv("MCP_ALLOWED_ORIGINS", "")
    return {o.strip().rstrip("/").lower() for o in raw.split(",") if o.strip()}


def _header(scope: Scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


def origin_allowed(scope: Scope) -> bool:
    origin = _header(scope, b"origin")
    if not origin or origin == "null":
        # 原生客户端不带 Origin;"null" 来自沙箱/file 页面,一律按跨站处理
        return origin is None
    origin = origin.rstrip("/").lower()
    if origin in _allowed_origins():
        return True
    host = (_header(scope, b"host") or "").lower()
    # 经反向代理时 Host 可能被改写,X-Forwarded-Host 才是浏览器看到的那个
    forwarded = (_header(scope, b"x-forwarded-host") or "").split(",")[0].strip().lower()
    return urlsplit(origin).netloc in {h for h in (host, forwarded) if h}


async def _send_json(send: Send, status: int, body: dict, *, www_authenticate: bool = False) -> None:
    headers = [(b"content-type", b"application/json")]
    if www_authenticate:
        headers.append((b"www-authenticate", b'Bearer realm="QuestionBank MCP"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": json.dumps(body).encode("utf-8")})


def _bearer(scope: Scope) -> Optional[str]:
    authorization = _header(scope, b"authorization") or ""
    if authorization[:7].lower() != "bearer ":
        return None
    token = authorization[7:].strip()
    return token or None


class McpAuthMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not origin_allowed(scope):
            await _send_json(send, 403, {"detail": "Origin not allowed", "code": "mcp.origin_forbidden"})
            return

        token = _bearer(scope)
        if token is None or not looks_like_api_key(token):
            await _send_json(
                send, 401,
                {"detail": "Missing or malformed API key", "code": "auth.not_authenticated"},
                www_authenticate=True,
            )
            return

        async with db_session.get_sessionmaker()() as db:
            if not await is_mcp_enabled(db):
                await _send_json(send, 403, {"detail": "MCP service is disabled", "code": "mcp.disabled"})
                return
            row = await crud_api_key.get_by_plaintext(db, key=token)
            if row is None:
                await _send_json(
                    send, 401,
                    {"detail": "Invalid API key", "code": "auth.token_invalid"},
                    www_authenticate=True,
                )
                return
            user = await crud_user.get(db, id=row.user_id)
            if user is None or not user.is_active:
                await _send_json(send, 403, {"detail": "Inactive user", "code": "auth.inactive_user"})
                return
            auth = McpAuth(
                user_id=user.id, key_id=row.id, key_prefix=row.prefix, base_url=public_base_url(scope)
            )
            await crud_api_key.touch(db, api_key=row)

        scope = dict(scope)
        scope[SCOPE_KEY] = auth
        await self.app(scope, receive, send)
