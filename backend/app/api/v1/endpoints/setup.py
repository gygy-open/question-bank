"""First-run setup wizard endpoints.

These are the only API routes reachable before the application has a database
configured. Once ``is_configured()`` is true they refuse to run again, so a
provisioned deployment (env ``DB_URL`` / existing ``config.json``) never exposes
them.
"""

import logging
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from starlette.concurrency import run_in_threadpool

from app.core.config import default_sqlite_url, is_configured, save_runtime_config
from app.crud.crud_user import user as crud_user
from app.db.migrations import run_migrations
from app.db.session import get_sessionmaker, reset_engine
from app.schemas.user import UserCreate

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


class SetupComplete(DBConfig):
    admin_username: str = Field(min_length=1)
    admin_password: str = Field(min_length=6)


def _build_url(cfg: DBConfig) -> str:
    if cfg.db_type == "sqlite":
        return default_sqlite_url()
    if not cfg.mysql:
        raise HTTPException(status_code=400, detail="mysql connection details are required")
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
    return {"configured": is_configured()}


@router.post("/test-db")
async def test_db(cfg: DBConfig) -> dict:
    url = _build_url(cfg)
    try:
        await _test_connection(url)
    except Exception as exc:  # noqa: BLE001 - surface the driver error to the wizard
        raise HTTPException(status_code=400, detail=f"Connection failed: {exc}") from exc
    return {"ok": True}


@router.post("/complete")
async def complete_setup(payload: SetupComplete) -> dict:
    if is_configured():
        raise HTTPException(status_code=400, detail="Application is already configured")

    url = _build_url(payload)

    # 1. Verify the database is reachable before persisting anything.
    try:
        await _test_connection(url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Connection failed: {exc}") from exc

    # 2. Persist the connection so subsequent boots start in normal mode.
    save_runtime_config({"db_url": url, "db_type": payload.db_type})

    # 3. Apply migrations (sync Alembic — run off the event loop).
    try:
        await run_in_threadpool(run_migrations, url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Migration failed: {exc}") from exc

    # 4. Rebuild the engine against the freshly configured database.
    await reset_engine(url)

    # 5. Create the initial superuser.
    session_maker = get_sessionmaker()
    async with session_maker() as db:
        existing = await crud_user.get_by_username(db, username=payload.admin_username)
        if not existing:
            await crud_user.create(
                db,
                obj_in=UserCreate(
                    username=payload.admin_username,
                    password=payload.admin_password,
                    is_superuser=True,
                    is_active=True,
                ),
            )

    logger.info("First-run setup completed (db_type=%s)", payload.db_type)
    return {"ok": True}
