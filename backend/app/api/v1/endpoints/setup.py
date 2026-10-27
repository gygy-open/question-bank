"""First-run setup wizard endpoints.

Initialization has two independent stages:

1. Database: ``/setup/database`` only runs while no database is configured, so a
   provisioned deployment (env ``DB_URL`` / existing ``config.json``) skips it.
2. First administrator: ``/setup/admin`` only runs once a database is configured
   and no active superuser exists, regardless of how the database was provided.

These are the only API routes reachable until both stages are complete.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.concurrency import run_in_threadpool

from app.api import deps
from app.core.api_errors import ApiError, ErrorCode
from app.core.config import default_sqlite_url, is_configured, save_runtime_config
from app.db.migrations import run_migrations
from app.db.session import reset_engine
from app.services import setup_state

logger = logging.getLogger(__name__)

router = APIRouter()


class MySQLConfig(BaseModel):
    host: str = "localhost"
    port: int = 3306
    user: str
    password: str
    database: str


class DBConfig(BaseModel):
    db_type: Literal["sqlite", "mysql"]
    mysql: Optional[MySQLConfig] = None


class AdminCreate(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=6)


def _build_url(cfg: DBConfig) -> str:
    if cfg.db_type == "sqlite":
        return default_sqlite_url()
    if not cfg.mysql:
        raise ApiError(400, ErrorCode.SETUP_MYSQL_REQUIRED, "mysql connection details are required")
    m = cfg.mysql
    return f"mysql+aiomysql://{m.user}:{m.password}@{m.host}:{m.port}/{m.database}"


async def _test_connection(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@router.get("/status")
async def setup_status() -> dict:
    db_configured = is_configured()
    admin_initialized = db_configured and await setup_state.is_admin_ready()
    return {"db_configured": db_configured, "admin_initialized": admin_initialized}


@router.post("/test-db")
async def test_db(cfg: DBConfig) -> dict:
    url = _build_url(cfg)
    try:
        await _test_connection(url)
    except Exception as exc:  # noqa: BLE001 - surface the driver error to the wizard
        raise ApiError(
            400, ErrorCode.SETUP_CONNECTION_FAILED, f"Connection failed: {exc}", {"error": str(exc)}
        ) from exc
    return {"ok": True}


@router.post("/database")
async def configure_database(cfg: DBConfig) -> dict:
    if is_configured():
        raise ApiError(400, ErrorCode.SETUP_DB_ALREADY_CONFIGURED, "Database is already configured")

    url = _build_url(cfg)

    try:
        await _test_connection(url)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            400, ErrorCode.SETUP_CONNECTION_FAILED, f"Connection failed: {exc}", {"error": str(exc)}
        ) from exc

    # Migrate before persisting so a failure leaves the app in setup mode and
    # the wizard can simply be retried.
    try:
        await run_in_threadpool(run_migrations, url)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(
            500, ErrorCode.SETUP_MIGRATION_FAILED, f"Migration failed: {exc}", {"error": str(exc)}
        ) from exc

    save_runtime_config({"db_url": url, "db_type": cfg.db_type})
    await reset_engine(url)

    logger.info("Database configured via setup wizard (db_type=%s)", cfg.db_type)
    return {"ok": True}


def _require_db_configured() -> None:
    if not is_configured():
        raise ApiError(400, ErrorCode.SETUP_DB_NOT_CONFIGURED, "Database is not configured yet")


@router.post("/admin", dependencies=[Depends(_require_db_configured)])
async def create_first_admin(payload: AdminCreate, db: deps.SessionDep) -> dict:
    username = payload.username.strip()
    if not username:
        raise ApiError(400, ErrorCode.SETUP_USERNAME_REQUIRED, "Username is required")
    try:
        await setup_state.create_first_superuser(
            db, username=username, password=payload.password
        )
    except setup_state.AdminAlreadyInitialized as exc:
        raise ApiError(400, ErrorCode.SETUP_ADMIN_INITIALIZED, "Administrator is already initialized") from exc
    except setup_state.UsernameTaken as exc:
        raise ApiError(400, ErrorCode.SETUP_USERNAME_EXISTS, "Username already exists") from exc

    # 学科不再预置：首次登录后由前端引导页 (/onboarding) 让用户创建第一个学科。
    logger.info("First superuser created via setup wizard")
    return {"ok": True}
