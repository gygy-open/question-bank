import sys
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
# Add the project root directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app._version import __version__
from app.api import legacy_media
from app.api.v1.api import api_router
from app.core.api_errors import ApiError, ErrorCode
from app.core.locale import LocaleMiddleware
from app.capabilities.errors import DomainError, status_for
from app.core.config import settings, is_configured
from app.core import storage
from app.services import setup_state
from app.services.embedding import reload_embedding_function
from app.mcp_server import MCP_PATH, mcp_asgi_app, run_mcp
from app.mcp_server import uploads as mcp_uploads
from starlette.routing import Route

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: only touch the database once the app has been configured.
    # Before first-run setup there is no database to talk to.
    removed = storage.cleanup_stale_tmp()
    if removed:
        logger.info("Removed %d stale temporary entries", removed)
    if is_configured():
        await reload_embedding_function()
    else:
        logger.warning("No database configured yet - starting in setup mode.")

    # MCP 会话管理器不依赖数据库,setup 模式下也照常启动;请求会被 require_setup 拦下。
    async with run_mcp():
        yield
    # Shutdown

app = FastAPI(title="QuestionBank API", version=__version__, lifespan=lifespan)
app.add_middleware(LocaleMiddleware)


@app.exception_handler(DomainError)
async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
    """领域错误 → HTTP。端点因此可以直接 await capabilities.run(...) 而不用 try/except。"""
    content: dict = {"detail": exc.detail}
    if exc.code:
        content["code"] = exc.code
        if exc.params:
            content["params"] = exc.params
    return JSONResponse(status_code=status_for(exc), content=content)


def _clean_validation_error(error: dict) -> dict:
    """只保留前端翻译需要的字段。``input`` 可能含密码等敏感值,不能原样回显。"""
    cleaned: dict = {"type": error.get("type"), "loc": list(error.get("loc", ())), "msg": error.get("msg")}
    ctx = {
        k: v
        for k, v in (error.get("ctx") or {}).items()
        if isinstance(v, (str, int, float, bool))
    }
    if ctx:
        cleaned["ctx"] = ctx
    return cleaned


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """422:``detail`` 仍是 pydantic 错误列表(兼容旧客户端),另附 ``code`` 让前端按 ``type`` 翻译。"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": [_clean_validation_error(e) for e in exc.errors()],
            "code": ErrorCode.VALIDATION_FAILED,
        },
    )


@app.exception_handler(ApiError)
async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    """带错误码的 HTTPException:在原 ``detail`` 之外附带 ``code`` / ``params``。"""
    content: dict = {"detail": exc.detail, "code": exc.code}
    if exc.params:
        content["params"] = exc.params
    return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)


_SETUP_PREFIX = f"{settings.API_V1_STR}/setup"
# Endpoints that must work even before first-run setup (e.g. version/update check).
_SETUP_EXEMPT = (
    _SETUP_PREFIX,
    f"{settings.API_V1_STR}/system/version",
    f"{settings.API_V1_STR}/system/desktop-locale",
)


@app.middleware("http")
async def require_setup(request: Request, call_next):
    """Block API calls (except the setup wizard and exempt endpoints) until
    initialization is complete, so the frontend can redirect to /setup:

    - no database configured        -> 503 ``setup_required``
    - database but no active admin  -> 503 ``admin_required``
    """
    path = request.url.path
    if path.startswith("/api") and not path.startswith(_SETUP_EXEMPT):
        if not is_configured():
            return JSONResponse(status_code=503, content={"detail": "setup_required"})
        if not await setup_state.is_admin_ready():
            return JSONResponse(status_code=503, content={"detail": "admin_required"})
    return await call_next(request)

# Ensure static directories exist
settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 旧媒体 URL 需鉴权,路由先于 /static 挂载注册。
app.include_router(legacy_media.router)
# Mount static files (absolute paths so serving is independent of the CWD,
# which matters for a packaged desktop build).
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")
# 导入源文件是私有数据,不再静态挂载;经 GET /api/v1/imports/{id}/source 鉴权下载。

app.include_router(api_router, prefix="/api/v1")

# 外部 AI 客户端经 MCP 接入(与 API 同端口)。用 Route 而非 Mount:Mount 会把 /api/mcp
# 307 重定向到 /api/mcp/,部分客户端的 POST 不跟随重定向。
# 预签名上传(令牌在路径里,不经 MCP 鉴权中间件),见 app/mcp_server/uploads.py
app.include_router(mcp_uploads.router, prefix=MCP_PATH + "/uploads", include_in_schema=False)
for _mcp_path in (MCP_PATH, MCP_PATH + "/"):
    app.router.routes.append(
        Route(_mcp_path, endpoint=mcp_asgi_app, methods=["GET", "POST", "DELETE"], include_in_schema=False)
    )


def _resolve_frontend_dir() -> Path | None:
    """Locate the built Nuxt SPA (``nuxi generate`` -> ``.output/public``).

    Resolution order: explicit ``FRONTEND_DIST`` env > bundled resources in a
    frozen desktop build > the sibling ``frontend/.output/public`` in dev.
    Returns ``None`` when no build is present (e.g. running the API standalone),
    so the backend still works without a compiled frontend.
    """
    candidates = []
    if os.getenv("FRONTEND_DIST"):
        candidates.append(Path(os.environ["FRONTEND_DIST"]))
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS")) / "frontend")
    candidates.append(Path(__file__).resolve().parents[2] / "frontend" / ".output" / "public")
    for c in candidates:
        if (c / "index.html").exists():
            return c
    return None


FRONTEND_DIR = _resolve_frontend_dir()

if FRONTEND_DIR is not None:
    _nuxt_assets = FRONTEND_DIR / "_nuxt"
    if _nuxt_assets.is_dir():
        app.mount("/_nuxt", StaticFiles(directory=_nuxt_assets), name="nuxt-assets")

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        # Backend routes are matched before this catch-all; guard anyway.
        if full_path.startswith(("api/", "static/", "uploads/", "_nuxt/")):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        # Serve real public files (favicon, logo.svg, ...) when they exist,
        # otherwise fall back to index.html for SPA client-side routing.
        candidate = FRONTEND_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIR / "index.html")
else:
    @app.get("/")
    def read_root():
        return {"message": "Welcome to QuestionBank API"}
