import sys
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager
# Add the project root directory to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.v1.api import api_router
from app.core.config import settings, is_configured
from app.services.embedding import reload_embedding_function

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: only touch the database once the app has been configured.
    # Before first-run setup there is no database to talk to.
    if is_configured():
        await reload_embedding_function()
    else:
        logger.warning("No database configured yet - starting in setup mode.")

    yield
    # Shutdown

app = FastAPI(title="Question Bank API", lifespan=lifespan)


_SETUP_PREFIX = f"{settings.API_V1_STR}/setup"


@app.middleware("http")
async def require_setup(request: Request, call_next):
    """Until a database is configured, block all API calls except the setup
    wizard so the frontend can detect first-run state and redirect to /setup."""
    if not is_configured():
        path = request.url.path
        if path.startswith("/api") and not path.startswith(_SETUP_PREFIX):
            return JSONResponse(status_code=503, content={"detail": "setup_required"})
    return await call_next(request)

# Ensure static directories exist
settings.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files (absolute paths so serving is independent of the CWD,
# which matters for a packaged desktop build).
app.mount("/static", StaticFiles(directory=settings.STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

app.include_router(api_router, prefix="/api/v1")


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
        return {"message": "Welcome to Question Bank API"}
