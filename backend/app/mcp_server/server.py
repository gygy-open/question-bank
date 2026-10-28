"""MCP 服务端 —— 低层 `Server` + Streamable HTTP(无状态、JSON 响应)。

挂载方式见 `app.main`:`/api/mcp` 路由 → `McpAuthMiddleware` → 会话管理器。
会话管理器只能 `run()` 一次,因此在 `run_mcp()`(由 FastAPI lifespan 调用)里按需新建。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

import mcp.types as types
from mcp.server import Server, ServerRequestContext
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.types import Receive, Scope, Send

from app._version import __version__
from app.capabilities.context import ExecutionContext, Surface
from app.crud.crud_user import user as crud_user
from app.db import session as db_session
from app.services.activity_logger import log_activity

from .auth import SCOPE_KEY, McpAuth, McpAuthMiddleware, current_auth
from .tools import McpTool, all_tools, error_payload, to_text

logger = logging.getLogger(__name__)

# 面向模型,统一用英文;不随界面语言翻译。
INSTRUCTIONS = """\
MCP server of QuestionBank, a question bank and paper composition system.
You act with exactly the permissions of the user who owns the API key.

Guidelines:
1. Call list_subjects first to get the subject IDs you can access; most tools need a subject_id.
2. scope_type for composition tools: shared = shared with the subject team, personal = visible only to the user.
3. To build a paper: composition_create, then composition_write_nodes with headings, text and question IDs.
   Before modifying a composition, read its latest revision with get_composition and pass it as expected_revision (optimistic locking).
4. New questions are drafts by default and must be reviewed in the system before they are published.
   To include an image or audio in a question, get an upload URL with create_media_upload_url, upload the local file
   with curl, then put the returned node into the question content.
5. Duplicate check: creating or editing a question fails with code question.duplicate_suspected when the
   bank already has a duplicate or highly similar question (params.candidates lists them; `variant` means
   numbers/formulas differ). Show the candidates to the user and ask. Only if the user confirms, retry with
   allow_duplicate=true (inside `data` for question_update). Never set allow_duplicate on your own.
   check_question_duplicates checks a draft in advance. If a candidate is the same question, prefer reusing
   its ID (e.g. in a composition) instead of creating a copy.
6. Delete tools remove data from the user's view (questions and compositions can only be restored inside the system); confirm with the user before running them.
7. Content (question text, titles, etc.) may be in any language; keep the user's language when writing content.
"""


def _auth_from(ctx: ServerRequestContext[Any, Any]) -> Optional[McpAuth]:
    request = getattr(ctx, "request", None)
    scope = getattr(request, "scope", None) or {}
    auth = scope.get(SCOPE_KEY)
    return auth if isinstance(auth, McpAuth) else None


def _client_ip(ctx: ServerRequestContext[Any, Any]) -> Optional[str]:
    request = getattr(ctx, "request", None)
    client = getattr(request, "client", None)
    return getattr(client, "host", None)


def _tool_definition(tool: McpTool) -> types.Tool:
    return types.Tool(
        name=tool.name,
        description=tool.description,
        input_schema=tool.input_schema,
        annotations=types.ToolAnnotations(
            read_only_hint=tool.read_only,
            destructive_hint=tool.destructive if not tool.read_only else None,
            open_world_hint=False,
        ),
    )


def _result(data: Dict[str, Any], *, is_error: bool = False) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=to_text(data))],
        structured_content=None if is_error else data,
        is_error=is_error,
    )


async def list_tools(
    ctx: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    return types.ListToolsResult(tools=[_tool_definition(t) for t in all_tools().values()])


async def call_tool(
    ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
) -> types.CallToolResult:
    auth = _auth_from(ctx)
    if auth is None:
        return _result({"status": 401, "detail": "Not authenticated"}, is_error=True)
    tool = all_tools().get(params.name)
    if tool is None:
        return _result({"status": 404, "detail": f"Unknown tool: {params.name}"}, is_error=True)
    return await execute_tool(tool, auth, params.arguments or {}, ip=_client_ip(ctx))


async def execute_tool(
    tool: McpTool, auth: McpAuth, args: Dict[str, Any], *, ip: Optional[str] = None
) -> types.CallToolResult:
    """每次调用独立会话、重新加载用户:撤销 Key / 停用用户 / 调整权限都立即生效。"""
    async with db_session.get_sessionmaker()() as db:
        user = await crud_user.get_with_memberships(db, id=auth.user_id)
        if user is None or not user.is_active:
            return _result({"status": 403, "detail": "Inactive user"}, is_error=True)

        ctx = ExecutionContext(db=db, actor=user, surface=Surface.MCP)
        error: Optional[Dict[str, Any]] = None
        data: Dict[str, Any] = {}
        auth_token = current_auth.set(auth)
        try:
            data = await tool.handler(ctx, args)
        except Exception as exc:  # noqa: BLE001 - 失败要回给客户端,而不是断开连接
            await db.rollback()
            error = error_payload(exc)
            if error.get("status", 500) >= 500:
                logger.exception("MCP tool %s failed", tool.name)
        finally:
            current_auth.reset(auth_token)

        # 只读调用频繁且无副作用,只审计写操作(含失败的写尝试)
        if not tool.read_only:
            try:
                await log_activity(
                    db, auth.user_id, "mcp_call", "mcp_tool",
                    details={
                        "tool": tool.name,
                        "key": auth.key_prefix,
                        "ok": error is None,
                        **({"error": error.get("code") or error.get("status")} if error else {}),
                    },
                    ip_address=ip,
                )
                await db.commit()
            except Exception:  # noqa: BLE001
                await db.rollback()
                logger.exception("Failed to write MCP audit log for %s", tool.name)

    if error is not None:
        return _result(error, is_error=True)
    return _result(data)


server: Server[Any] = Server(
    "QuestionBank",
    version=__version__,
    title="QuestionBank",
    instructions=INSTRUCTIONS,
    on_list_tools=list_tools,
    on_call_tool=call_tool,
)

_manager: Optional[StreamableHTTPSessionManager] = None


@asynccontextmanager
async def run_mcp() -> AsyncIterator[None]:
    global _manager
    manager = StreamableHTTPSessionManager(app=server, json_response=True, stateless=True)
    async with manager.run():
        _manager = manager
        try:
            yield
        finally:
            _manager = None


async def _transport(scope: Scope, receive: Receive, send: Send) -> None:
    if _manager is None:
        await send({"type": "http.response.start", "status": 503, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": b'{"detail":"MCP service is not running"}'})
        return
    await _manager.handle_request(scope, receive, send)


mcp_asgi_app = McpAuthMiddleware(_transport)
