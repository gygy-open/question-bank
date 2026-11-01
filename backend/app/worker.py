import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Dict, Optional
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

# Add backend directory to path so we can import app modules
sys.path.append(str(Path(__file__).parent.parent))

from app.core.locale import set_locale
from app.db.session import SessionLocal
from app.core.config import get_db_url, is_configured
from app.crud.crud_user import user as crud_user
from app.models.import_task import ImportMethod, ImportPauseReason, ImportTask, ImportTaskStatus
from app.models.user import User
from app.services import data_migrations
from app.services import import_task_service as tasks_svc
from app.services.ai_errors import classify_ai_error
from app.services.ai_resolver import resolve_provider_id
from app.services.doc_processor import doc_processor
from app.services.embedding import reload_embedding_function
from app.services.paper_import_service import commit_extracted_paper_import
from app.services.structured_parser import has_structured_tags

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 正在处理的任务被取消/删除后,最迟这么久停下来。
CANCEL_POLL_SECONDS = 2.0
# 空闲时轮询队列的间隔。
IDLE_POLL_SECONDS = 3.0
# 同一服务商连续出现这么多次无法归类的错误,视为服务故障并暂停它的其余任务。
UNKNOWN_ERROR_THRESHOLD = 3


class ProviderBreaker:
    """按服务商统计连续的未知错误;worker 单进程串行,放内存即可。"""

    def __init__(self, threshold: int = UNKNOWN_ERROR_THRESHOLD) -> None:
        self.threshold = threshold
        self._failures: Dict[Optional[int], int] = {}

    def failure(self, provider_id: Optional[int]) -> bool:
        """记一次失败;达到阈值时返回 True 并清零。"""
        count = self._failures.get(provider_id, 0) + 1
        if count >= self.threshold:
            self._failures.pop(provider_id, None)
            return True
        self._failures[provider_id] = count
        return False

    def success(self, provider_id: Optional[int]) -> None:
        self._failures.pop(provider_id, None)


class _TaskStopped(Exception):
    """任务已不在处理中(被取消、删除或重置),放弃本次结果。"""


async def _update_processing(db: AsyncSession, task_id: int, **values: Any) -> bool:
    """只在任务仍处于处理中时写入;返回是否写入成功。不提交。"""
    values.setdefault("updated_at", datetime.utcnow())
    result = await db.execute(
        update(ImportTask)
        .where(ImportTask.id == task_id, ImportTask.status == ImportTaskStatus.PROCESSING)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return bool(result.rowcount)


async def _set_stage(db: AsyncSession, task_id: int, stage: str, method: Optional[str] = None) -> None:
    if not await _update_processing(db, task_id, progress=tasks_svc.dump_progress(stage=stage, method=method)):
        await db.rollback()
        raise _TaskStopped()
    await db.commit()


async def _fail(
    db: AsyncSession,
    task_id: int,
    message: str,
    *,
    error_code: Optional[str] = None,
    method: Optional[str] = None,
) -> None:
    await db.rollback()
    await _update_processing(
        db,
        task_id,
        status=ImportTaskStatus.FAILED,
        error_message=message[:4000] if message else None,
        progress=tasks_svc.dump_progress(stage="failed", method=method, error_code=error_code),
    )
    await db.commit()


async def _pause(
    db: AsyncSession, task_id: int, reason: ImportPauseReason, provider_id: Optional[int], message: str
) -> None:
    await db.rollback()
    count = await tasks_svc.pause_for_provider(
        db, task_id=task_id, reason=reason, provider_id=provider_id, message=message[:4000] if message else None
    )
    await db.commit()
    logger.warning(
        "Paused %d import task(s) for provider %s (%s): %s", count, provider_id, reason.value, message
    )


def _decide_method(task: ImportTask, source: tasks_svc.IngestedSource) -> str:
    method = tasks_svc.method_of(task)
    if method != ImportMethod.AUTO.value:
        return method
    return ImportMethod.STRUCTURED.value if has_structured_tags(source.markdown) else ImportMethod.AI.value


async def _handle_ai_error(
    db: AsyncSession,
    task_id: int,
    exc: Exception,
    *,
    provider_id: Optional[int],
    method: str,
    breaker: ProviderBreaker,
) -> None:
    kind = classify_ai_error(exc)
    message = str(exc) or exc.__class__.__name__
    if kind.category in ("provider", "transient"):
        # transient 能走到这里说明重试已耗尽,按服务故障处理。
        await _pause(db, task_id, kind.reason or ImportPauseReason.UNAVAILABLE, provider_id, message)
        return
    if kind.category == "document":
        breaker.success(provider_id)
        await _fail(db, task_id, message, error_code=tasks_svc.ERROR_AI_DOCUMENT, method=method)
        return
    if breaker.failure(provider_id):
        await _pause(db, task_id, ImportPauseReason.UNAVAILABLE, provider_id, message)
        return
    await _fail(db, task_id, message, error_code=tasks_svc.ERROR_AI_UNKNOWN, method=method)


async def _run_task(db: AsyncSession, task: ImportTask, breaker: ProviderBreaker) -> None:
    # 失败路径会 rollback 并使 ORM 对象过期,之后只用这里取出的普通值。
    task_id = task.id
    user_id = task.user_id
    subject_id = task.subject_id
    try:
        source = await tasks_svc.ingest_task_source(db, task)
    except tasks_svc.SourceUnavailable as exc:
        await _fail(db, task_id, str(exc), error_code=tasks_svc.ERROR_SOURCE_UNAVAILABLE)
        return
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.exception("Import task %s: failed to read the document", task_id)
        await _fail(db, task_id, str(exc) or exc.__class__.__name__, error_code=tasks_svc.ERROR_PARSE_FAILED)
        return

    method = _decide_method(task, source)
    provider_id: Optional[int] = None
    if method == ImportMethod.AI.value:
        provider_id = await resolve_provider_id(
            db, user_id=user_id, purpose=tasks_svc.purpose_of(task)  # type: ignore[arg-type]
        )
        if provider_id is None:
            await _pause(db, task_id, ImportPauseReason.MODEL, None, "No AI model is configured")
            return
    await _set_stage(db, task_id, "extracting", method)

    async def on_stage(stage: str) -> None:
        await _set_stage(db, task_id, stage, method)

    try:
        extraction = await doc_processor.extractor_for(method).extract(
            source.markdown,
            db,
            image_data=source.image_data,
            filename=source.filename,
            mode=task.mode or "extract",
            subject_id=subject_id,
            user_id=user_id,
            on_stage=on_stage,
        )
    except (asyncio.CancelledError, _TaskStopped):
        raise
    except Exception as exc:
        if method == ImportMethod.AI.value:
            logger.exception("Import task %s: AI extraction failed", task_id)
            await _handle_ai_error(db, task_id, exc, provider_id=provider_id, method=method, breaker=breaker)
        else:
            logger.exception("Import task %s: structured parsing failed", task_id)
            await _fail(db, task_id, str(exc), error_code=tasks_svc.ERROR_PARSE_FAILED, method=method)
        return

    if provider_id is not None:
        breaker.success(provider_id)
        resumed = await tasks_svc.resume_provider(db, provider_id)
        if resumed:
            logger.info("AI provider %s works again; resumed %d paused task(s)", provider_id, resumed)

    count = len(extraction.questions or [])
    if count == 0:
        await _fail(
            db, task_id, "No questions were found in the document",
            error_code=tasks_svc.ERROR_NO_QUESTIONS, method=method,
        )
        return

    if task.auto_commit:
        await _commit_directly(db, task, extraction, method=method, count=count)
        return

    payload = tasks_svc.review_payload(task, source, extraction, method=method)
    result_sha256 = await asyncio.to_thread(tasks_svc.save_result, payload)
    written = await _update_processing(
        db,
        task_id,
        status=ImportTaskStatus.REVIEW_READY,
        result_sha256=result_sha256,
        provider_id=provider_id,
        error_message=None,
        progress=tasks_svc.dump_progress(stage="ready", method=method, count=count),
    )
    if not written:
        await db.rollback()
        raise _TaskStopped()
    await db.commit()
    logger.info("Import task %s ready for review: %d question(s)", task_id, count)


async def _commit_directly(db: AsyncSession, task: ImportTask, extraction: Any, *, method: str, count: int) -> None:
    """识别后直接入库(跳过审核)。"""
    task_id = task.id
    # 查重要读用户的学科成员关系,异步会话里必须预加载。
    user = await crud_user.get_with_memberships(db, id=task.user_id) if task.user_id else None
    if user is None or task.subject_id is None:
        await _fail(db, task_id, "Import task requires a user and a subject", method=method)
        return
    current = await db.scalar(select(ImportTask.status).where(ImportTask.id == task_id))
    if current != ImportTaskStatus.PROCESSING:
        await db.rollback()
        raise _TaskStopped()
    try:
        report = await commit_extracted_paper_import(
            db,
            actor=user,
            subject_id=task.subject_id,
            extraction={
                "questions": extraction.questions,
                "paper": extraction.paper,
                "stimuli": extraction.stimuli,
                "question_groups": extraction.question_groups,
            },
            import_task=task,
        )
    except Exception as exc:
        logger.exception("Import task %s: failed to save questions", task_id)
        await _fail(db, task_id, str(exc) or exc.__class__.__name__, method=method)
        return
    task.progress = tasks_svc.dump_progress(stage="done", method=method, count=count)
    task.updated_at = datetime.utcnow()
    await db.commit()
    logger.info(
        "Import task %s completed. Saved %d questions, %d skipped.",
        task_id, len(report.created_questions), len(report.skipped),
    )


async def _watch_for_cancel(
    task_id: int,
    runner: "asyncio.Future[Any]",
    session_factory: Callable[[], Any],
    interval: float,
) -> bool:
    """任务被取消/删除/重置时中止正在执行的 runner;返回是否由它中止。"""
    while not runner.done():
        await asyncio.sleep(interval)
        if runner.done():
            break
        try:
            async with session_factory() as session:
                status = await session.scalar(select(ImportTask.status).where(ImportTask.id == task_id))
        except Exception:  # noqa: BLE001 - 查询失败就等下一轮
            continue
        if status in (None, ImportTaskStatus.CANCELLED, ImportTaskStatus.PENDING):
            runner.cancel()
            return True
    return False


async def process_task(
    db: AsyncSession,
    task: ImportTask,
    *,
    breaker: Optional[ProviderBreaker] = None,
    session_factory: Optional[Callable[[], Any]] = None,
    cancel_poll_seconds: Optional[float] = CANCEL_POLL_SECONDS,
) -> None:
    task_id = task.id
    logger.info(f"Starting task {task_id} ({task.file_type}): {task.original_filename}")
    task.status = ImportTaskStatus.PROCESSING
    task.error_message = None
    task.paused_reason = None
    task.progress = tasks_svc.dump_progress(stage="parsing")
    task.updated_at = datetime.utcnow()
    if task.subject_id is None and task.user_id:
        # 早期任务没有记录学科,沿用用户当前学科。
        user = await db.get(User, task.user_id)
        task.subject_id = user.last_active_subject_id if user else None
    await db.commit()
    set_locale(task.locale)

    runner = asyncio.ensure_future(_run_task(db, task, breaker or ProviderBreaker()))
    watcher = (
        asyncio.ensure_future(
            _watch_for_cancel(task_id, runner, session_factory or SessionLocal, cancel_poll_seconds)
        )
        if cancel_poll_seconds
        else None
    )
    try:
        await runner
    except _TaskStopped:
        await db.rollback()
        logger.info("Import task %s stopped before finishing", task_id)
    except asyncio.CancelledError:
        stopped_by_user = watcher is not None and watcher.done() and not watcher.cancelled() and watcher.result()
        if not stopped_by_user:
            raise
        await db.rollback()
        logger.info("Import task %s was cancelled while running", task_id)
    except Exception as exc:
        logger.exception("Import task %s crashed", task_id)
        await _fail(db, task_id, str(exc) or exc.__class__.__name__)
    finally:
        if watcher is not None and not watcher.done():
            watcher.cancel()


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
                await db.execute(text("SELECT 1 FROM import_tasks LIMIT 1"))
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

    # 一次性数据迁移在后台跑,不耽误导入任务;保留引用防止任务被回收。
    data_migration_task = asyncio.create_task(run_data_migrations())  # noqa: F841

    # Initialize Embedding Function
    try:
        await reload_embedding_function()
        logger.info("Embedding function initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize embedding function: {e}")

    logger.info("Worker waiting for tasks...")
    # SQLite does not support ``SELECT ... FOR UPDATE SKIP LOCKED``. In the
    # single-writer SQLite (desktop) case there is only one worker anyway, so
    # row-level locking is unnecessary; on MySQL we keep SKIP LOCKED so multiple
    # workers can pull tasks concurrently without contention.
    use_row_lock = not get_db_url().startswith("sqlite")
    if not use_row_lock:
        await _requeue_interrupted_tasks()

    breaker = ProviderBreaker()
    while True:
        async with SessionLocal() as db:
            try:
                resumed = await tasks_svc.resume_stale_unavailable(db)
                if resumed:
                    logger.info("Retrying %d import task(s) paused by an unreachable AI service", resumed)
                await db.commit()

                stmt = select(ImportTask).where(
                    ImportTask.status == ImportTaskStatus.PENDING,
                    ImportTask.source.in_(tasks_svc.QUEUE_SOURCES),
                )\
                    .order_by(ImportTask.created_at, ImportTask.id)\
                    .limit(1)
                if use_row_lock:
                    stmt = stmt.with_for_update(skip_locked=True)

                result = await db.execute(stmt)
                task = result.scalar_one_or_none()

                if task:
                    await process_task(db, task, breaker=breaker)
                else:
                    await db.commit()
                    await asyncio.sleep(IDLE_POLL_SECONDS)
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(5)


async def _requeue_interrupted_tasks() -> None:
    """单 worker(SQLite/桌面版)启动时,上次进程退出前没跑完的任务一定已经中断,放回队列。"""
    async with SessionLocal() as db:
        result = await db.execute(
            update(ImportTask)
            .where(
                ImportTask.status == ImportTaskStatus.PROCESSING,
                ImportTask.source.in_(tasks_svc.QUEUE_SOURCES),
            )
            .values(status=ImportTaskStatus.PENDING, progress=None, updated_at=datetime.utcnow())
        )
        await db.commit()
        if result.rowcount:
            logger.info("Re-queued %d import task(s) interrupted by the last shutdown", result.rowcount)

def main():
    """Blocking entry point. Importable so the packaged desktop launcher can run
    the worker in a child process (see the packaging plan)."""
    asyncio.run(worker())


if __name__ == "__main__":
    main()
