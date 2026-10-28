"""启动后的一次性数据迁移。

Alembic 只管表结构与可在 SQL 内完成的数据变换;需要读写文件、依赖应用服务或可能较慢的
数据任务放在这里,由 worker 在后台执行,不阻塞 API 启动。

- 每个任务成功后写入 system_settings 键 ``data_migration.<name>``(值为完成时间,
  description 为报告摘要),之后不再执行;任务本身也须幂等,标记丢失时重跑无害。
- 只在库结构已升级到 head 时执行;MySQL 上用 GET_LOCK 保证多进程/多副本只有一个在跑。
- 失败只记日志、不写标记,下次启动再试。
"""
from __future__ import annotations

import enum
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncIterator, Awaitable, Callable, List, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession

from app.models.system_setting import DATA_MIGRATION_KEY_PREFIX, SystemSetting
from app.services.question_dedup_core import DEDUP_VERSION

logger = logging.getLogger(__name__)

KEY_PREFIX = DATA_MIGRATION_KEY_PREFIX
_LOCK_NAME = "qb_data_migrations"
_KEY_MAX_LEN = 50
_DESCRIPTION_MAX_LEN = 255


@dataclass(frozen=True)
class DataMigration:
    name: str
    # 在给定会话中执行并提交迁移,返回写入标记 description 的一行摘要。
    run: Callable[[AsyncSession], Awaitable[str]]


class Outcome(enum.Enum):
    DONE = "done"            # 所有任务均已完成
    NOT_READY = "not_ready"  # 库结构尚未到 head 或其他进程正在执行,稍后重试
    SKIPPED = "skipped"      # 库结构比当前代码新,不执行
    FAILED = "failed"        # 有任务出错,下次启动再试


def flag_key(name: str) -> str:
    key = f"{KEY_PREFIX}{name}"
    if len(key) > _KEY_MAX_LEN:
        raise ValueError(f"data migration key too long (>{_KEY_MAX_LEN}): {key}")
    return key


async def is_done(db: AsyncSession, name: str) -> bool:
    return await db.get(SystemSetting, flag_key(name)) is not None


async def mark_done(db: AsyncSession, name: str, summary: str = "") -> None:
    """登记任务已完成(由调用方提交)。"""
    key = flag_key(name)
    value = datetime.now(timezone.utc).isoformat(timespec="seconds")
    description = summary[:_DESCRIPTION_MAX_LEN] or None
    setting = await db.get(SystemSetting, key)
    if setting is None:
        db.add(SystemSetting(key=key, value=value, description=description))
    else:
        setting.value = value
        setting.description = description


# --- 任务 -------------------------------------------------------------------------

async def _legacy_media_assets(db: AsyncSession) -> str:
    """把旧 /static/media 图片转为学科内容资产,使其出现在媒体库并登记引用。"""
    from app.services.media_migration import migrate_media

    report = await migrate_media(db, apply=True)
    for line in report.lines():
        logger.info("legacy_media_assets: %s", line)
    return report.summary()


async def _question_dedup(db: AsyncSession) -> str:
    """为存量题目补算查重签名;规则版本变化时任务名随之变化,会再跑一遍。"""
    from app.services.question_dedup import backfill

    count = await backfill(db)
    return f"backfilled {count} questions"


DATA_MIGRATIONS: List[DataMigration] = [
    DataMigration("legacy_media_assets", _legacy_media_assets),
    DataMigration(f"question_dedup_v{DEDUP_VERSION}", _question_dedup),
]


# --- 执行器 -----------------------------------------------------------------------

def _script_heads() -> tuple[set[str], Callable[[str], bool]]:
    from alembic.script import ScriptDirectory

    from app.db.migrations import _alembic_config

    script = ScriptDirectory.from_config(_alembic_config())

    def known(rev: str) -> bool:
        try:
            return script.get_revision(rev) is not None
        except Exception:  # noqa: BLE001 - 未知版本号
            return False

    return set(script.get_heads()), known


async def _schema_state(conn: AsyncConnection) -> Outcome:
    try:
        current = {row[0] for row in await conn.execute(text("SELECT version_num FROM alembic_version"))}
    except Exception:  # noqa: BLE001 - 表还没建
        return Outcome.NOT_READY
    heads, known = _script_heads()
    if current == heads:
        return Outcome.DONE
    if any(not known(rev) for rev in current):
        return Outcome.SKIPPED
    return Outcome.NOT_READY


@asynccontextmanager
async def _exclusive(engine: AsyncEngine) -> AsyncIterator[bool]:
    """MySQL:命名锁(连接级),拿不到说明别的进程在跑。SQLite 单写者,无需加锁。"""
    if engine.dialect.name != "mysql":
        yield True
        return
    async with engine.connect() as conn:
        acquired = (await conn.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": _LOCK_NAME})).scalar() == 1
        try:
            yield acquired
        finally:
            if acquired:
                await conn.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": _LOCK_NAME})


async def run_pending(
    *,
    engine: Optional[AsyncEngine] = None,
    sessionmaker: Optional[Callable[[], AsyncSession]] = None,
    migrations: Sequence[DataMigration] = DATA_MIGRATIONS,
    require_head: bool = True,
) -> Outcome:
    """按顺序执行尚未完成的数据迁移。"""
    if engine is None or sessionmaker is None:
        from app.db.session import SessionLocal, get_engine

        engine = engine or get_engine()
        sessionmaker = sessionmaker or SessionLocal

    if require_head:
        async with engine.connect() as conn:
            state = await _schema_state(conn)
        if state is Outcome.SKIPPED:
            logger.warning("Data migrations skipped: database schema is newer than this build.")
        if state is not Outcome.DONE:
            return state

    async with _exclusive(engine) as acquired:
        if not acquired:
            return Outcome.NOT_READY
        for migration in migrations:
            async with sessionmaker() as db:
                if await is_done(db, migration.name):
                    continue
                logger.info("Data migration %s: starting", migration.name)
                try:
                    summary = await migration.run(db)
                    await mark_done(db, migration.name, summary)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    logger.exception("Data migration %s failed; will retry on next start", migration.name)
                    return Outcome.FAILED
                logger.info("Data migration %s: done (%s)", migration.name, summary)
    return Outcome.DONE
