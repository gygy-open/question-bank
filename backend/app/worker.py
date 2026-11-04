"""后台 worker:轮询通用任务表 ``jobs``,按任务类型分派给处理器执行。

导入识别、题干拆解等所有后台工作都是 job;领取顺序按优先级(用户触发 > 入库自动 >
存量回填)和排队时间。AI 出错时的暂停 / 恢复 / 熔断由 ``app/services/jobs`` 统一处理。
"""
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend directory to path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.db.session import SessionLocal
from app.core.config import get_db_url, is_configured
from app.models.job import Job
from app.services import data_migrations
from app.services.embedding import reload_embedding_function
from app.services.jobs import (
    CANCEL_POLL_SECONDS,
    ProviderBreaker,
    job_service,
    load_handlers,
    run_job,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 空闲时轮询队列的间隔。
IDLE_POLL_SECONDS = 3.0

__all__ = ["ProviderBreaker", "main", "process_job", "worker"]


async def process_job(
    db: AsyncSession,
    job: Job,
    *,
    breaker: Optional[ProviderBreaker] = None,
    session_factory: Optional[Callable[[], Any]] = None,
    cancel_poll_seconds: Optional[float] = CANCEL_POLL_SECONDS,
) -> None:
    """执行一条已领取的 job(见 ``app.services.jobs.run_job``)。"""
    await run_job(
        db,
        job,
        breaker=breaker,
        session_factory=session_factory,
        cancel_poll_seconds=cancel_poll_seconds,
    )


async def wait_for_schema() -> None:
    """Block until the database schema has been migrated.

    ``is_configured()`` only tells us a database URL exists — the tables may not
    be there yet because migrations run in a *different* process (the backend
    entrypoint / the setup wizard) and can still be in progress. Probing a core
    table here prevents the worker from querying (and erroring on) tables that
    have not been created yet.
    """
    while True:
        try:
            async with SessionLocal() as db:
                await db.execute(text("SELECT 1 FROM jobs LIMIT 1"))
            return
        except Exception:
            logger.info("Worker: waiting for database schema (migrations)...")
            await asyncio.sleep(5)


async def run_data_migrations(*, retry_interval: float = 60, max_attempts: int = 60) -> None:
    """执行一次性数据迁移。库结构可能仍在另一个进程中升级,未就绪时定期重试。"""
    for _ in range(max_attempts):
        try:
            outcome = await data_migrations.run_pending()
        except Exception:
            logger.exception("Data migrations could not run")
            return
        if outcome is not data_migrations.Outcome.NOT_READY:
            return
        await asyncio.sleep(retry_interval)
    logger.warning("Data migrations still not ready; will retry on next start.")


async def worker():
    logger.info("Worker started, initializing...")

    # In a packaged desktop build the worker is spawned before the first-run
    # setup wizard has picked a database. Wait until the app is configured
    # before touching the DB or the embedding model.
    while not is_configured():
        logger.info("Worker: database not configured yet, waiting for setup...")
        await asyncio.sleep(5)

    # A configured URL does not guarantee the schema exists yet: migrations may
    # still be running in another process. Wait for the tables before touching
    # the DB or the embedding model (which reads ``system_settings``).
    await wait_for_schema()

    # 一次性数据迁移在后台跑,不耽误执行任务;保留引用防止任务被回收。
    data_migration_task = asyncio.create_task(run_data_migrations())  # noqa: F841

    # Initialize Embedding Function
    try:
        await reload_embedding_function()
        logger.info("Embedding function initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize embedding function: {e}")

    # 注册全部任务处理器;worker 只领取已注册类型的 job。
    load_handlers()

    logger.info("Worker waiting for jobs...")
    # SQLite does not support ``SELECT ... FOR UPDATE SKIP LOCKED``. In the
    # single-writer SQLite (desktop) case there is only one worker anyway, so
    # row-level locking is unnecessary; on MySQL we keep SKIP LOCKED so multiple
    # workers can pull jobs concurrently without contention.
    use_row_lock = not get_db_url().startswith("sqlite")
    if not use_row_lock:
        await _requeue_interrupted_jobs()

    breaker = ProviderBreaker()
    while True:
        async with SessionLocal() as db:
            try:
                resumed = await job_service.resume_stale_unavailable(db)
                if resumed:
                    logger.info("Retrying %d job(s) paused by an unreachable AI service", resumed)
                await db.commit()

                job = await job_service.claim_next(db, use_row_lock=use_row_lock)
                if job:
                    await process_job(db, job, breaker=breaker)
                else:
                    await db.commit()
                    await asyncio.sleep(IDLE_POLL_SECONDS)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(5)


async def _requeue_interrupted_jobs() -> None:
    """单 worker(SQLite/桌面版)启动时,上次进程退出前没跑完的 job 一定已经中断,放回队列。"""
    async with SessionLocal() as db:
        count = await job_service.requeue_running(db)
        await db.commit()
        if count:
            logger.info("Re-queued %d job(s) interrupted by the last shutdown", count)


def main():
    """Blocking entry point. Importable so the packaged desktop launcher can run
    the worker in a child process (see the packaging plan)."""
    asyncio.run(worker())


if __name__ == "__main__":
    main()
