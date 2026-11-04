"""执行一条 job:构造上下文、并行监视取消、统一处理结果与 AI 错误。

worker 每领取到一条 job 就调用 ``run_job``。处理器只关心业务逻辑,通过
``JobContext`` 汇报进度、成功、失败或暂停;取消检测、AI 错误分类、服务商熔断、
异常兜底都在这里统一完成。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import set_locale
from app.models.import_task import ImportPauseReason
from app.models.job import Job, JobStatus
from app.services.ai_errors import classify_ai_error

from . import service as job_service
from .registry import get_handler

logger = logging.getLogger(__name__)

# 正在执行的 job 被取消/删除后,最迟这么久停下来。
CANCEL_POLL_SECONDS = 2.0
# 同一服务商连续出现这么多次无法归类的错误,视为服务故障并暂停用到它的全部 job。
UNKNOWN_ERROR_THRESHOLD = 3

# 失败原因码:无法归类的 AI 错误 / 文档本身导致的 AI 错误(前端据此翻译)。
ERROR_AI_UNKNOWN = "ai_unknown"
ERROR_AI_DOCUMENT = "ai_document"


class JobStopped(Exception):
    """job 已不在执行中(被取消、删除或重置),放弃本次结果。"""


class ProviderBreaker:
    """按服务商统计连续的未知错误。worker 单进程串行执行,放内存即可。"""

    def __init__(self, threshold: int = UNKNOWN_ERROR_THRESHOLD) -> None:
        self.threshold = threshold
        self._failures: Dict[Optional[int], int] = {}

    # region 公共方法

    def failure(self, provider_id: Optional[int]) -> bool:
        """记一次失败;达到阈值时返回 True 并清零。"""
        count = self._failures.get(provider_id, 0) + 1
        if count >= self.threshold:
            self._failures.pop(provider_id, None)
            return True
        self._failures[provider_id] = count
        return False

    def success(self, provider_id: Optional[int]) -> None:
        """一次成功调用清零该服务商的计数。"""
        self._failures.pop(provider_id, None)

    # endregion


def dump_progress(**values: Any) -> str:
    """进度序列化为 JSON;值为 None 的键省略,前端只看到真正有的信息。"""
    return json.dumps({k: v for k, v in values.items() if v is not None}, ensure_ascii=False)


@dataclass
class JobContext:
    """一次执行的上下文。处理器通过它读取 job 信息、汇报进度与结果。

    job 的字段在构造时就复制成普通值:失败路径会 rollback,ORM 对象随之过期,
    之后再读属性会触发隐式 IO(异步会话下直接报错)。
    """

    db: AsyncSession
    job_id: int
    type: str
    target_type: Optional[str]
    target_id: Optional[int]
    user_id: Optional[int]
    subject_id: Optional[int]
    locale: Optional[str]
    attempts: int
    payload: Dict[str, Any] = field(default_factory=dict)
    breaker: ProviderBreaker = field(default_factory=ProviderBreaker)
    # 处理器是否已经显式结束了 job(成功/失败/暂停);为 False 时 runner 会兜底记为成功。
    finished: bool = False

    @classmethod
    def from_job(cls, db: AsyncSession, job: Job, breaker: ProviderBreaker) -> "JobContext":
        return cls(
            db=db,
            job_id=job.id,
            type=job.type,
            target_type=job.target_type,
            target_id=job.target_id,
            user_id=job.user_id,
            subject_id=job.subject_id,
            locale=job.locale,
            attempts=job.attempts or 0,
            payload=job_service.payload_of(job),
            breaker=breaker,
        )

    # region 公共方法:进度与结果

    async def set_progress(self, **progress: Any) -> None:
        """写入进度并提交。job 已被取消时抛出 ``JobStopped``。"""
        if not await job_service.update_running(self.db, self.job_id, progress=dump_progress(**progress)):
            await self.db.rollback()
            raise JobStopped()
        await self.db.commit()

    async def ensure_running(self) -> None:
        """job 已不在执行中时抛出 ``JobStopped``(只读检查,不写入)。"""
        status = await self.db.scalar(select(Job.status).where(Job.id == self.job_id))
        if status != JobStatus.RUNNING.value:
            await self.db.rollback()
            raise JobStopped()

    async def succeed(self, *, progress: Optional[Dict[str, Any]] = None, provider_id: Optional[int] = None) -> None:
        """把 job 标记为成功,**不提交**——处理器随后写入业务结果,再一起提交。

        job 已被取消时回滚并抛出 ``JobStopped``,处理器不应再写业务结果。
        """
        written = await job_service.finish(
            self.db,
            self.job_id,
            JobStatus.SUCCEEDED,
            progress=dump_progress(**progress) if progress is not None else None,
            provider_id=provider_id,
        )
        if not written:
            await self.db.rollback()
            raise JobStopped()
        self.finished = True

    async def fail(self, message: str, *, error_code: Optional[str] = None, **progress: Any) -> None:
        """把 job 标记为失败并提交。先回滚,丢弃执行到一半的写入。

        :param error_code: 失败原因码,写进进度供前端翻译;原始错误文本另存。
        :param progress: 额外写进进度的信息(例如导入方式 ``method``)。
        """
        await self.db.rollback()
        await job_service.finish(
            self.db,
            self.job_id,
            JobStatus.FAILED,
            error=message[:4000] if message else None,
            progress=dump_progress(stage="failed", error_code=error_code, **progress),
        )
        await self.db.commit()
        self.finished = True

    async def pause(self, reason: ImportPauseReason, provider_id: Optional[int], message: str) -> None:
        """AI 服务不可用:暂停本 job 和同一服务商上排队的其他 job,并提交。"""
        await self.db.rollback()
        count = await job_service.pause_for_provider(
            self.db,
            job_id=self.job_id,
            reason=reason,
            provider_id=provider_id,
            message=message[:4000] if message else None,
        )
        await self.db.commit()
        self.finished = True
        logger.warning(
            "Paused %d job(s) for provider %s (%s): %s", count, provider_id, reason.value, message
        )

    # endregion

    # region 公共方法:AI 调用结果

    async def ai_succeeded(self, provider_id: Optional[int]) -> None:
        """一次 AI 调用成功:清零熔断计数,并恢复之前因该服务商暂停的 job(提交)。"""
        if provider_id is None:
            return
        self.breaker.success(provider_id)
        resumed = await job_service.resume_provider(self.db, provider_id)
        await self.db.commit()
        if resumed:
            logger.info("AI provider %s works again; resumed %d paused job(s)", provider_id, resumed)

    async def handle_ai_error(self, exc: Exception, *, provider_id: Optional[int], **progress: Any) -> None:
        """按错误类别处理 AI 调用失败:

        - provider / transient(重试已耗尽):服务故障,暂停同一服务商的全部 job;
        - document:这份输入本身让 AI 出错,只让当前 job 失败;
        - 其他未知错误:先让当前 job 失败;同一服务商连续多次未知错误则视为服务故障暂停。
        """
        kind = classify_ai_error(exc)
        message = str(exc) or exc.__class__.__name__
        if kind.category in ("provider", "transient"):
            await self.pause(kind.reason or ImportPauseReason.UNAVAILABLE, provider_id, message)
            return
        if kind.category == "document":
            self.breaker.success(provider_id)
            await self.fail(message, error_code=ERROR_AI_DOCUMENT, **progress)
            return
        if self.breaker.failure(provider_id):
            await self.pause(ImportPauseReason.UNAVAILABLE, provider_id, message)
            return
        await self.fail(message, error_code=ERROR_AI_UNKNOWN, **progress)

    # endregion


async def run_job(
    db: AsyncSession,
    job: Job,
    *,
    breaker: Optional[ProviderBreaker] = None,
    session_factory: Optional[Callable[[], Any]] = None,
    cancel_poll_seconds: Optional[float] = CANCEL_POLL_SECONDS,
) -> None:
    """执行一条已领取(执行中)的 job,直到它结束、被取消或出错。

    :param session_factory: 取消监视用的独立会话工厂;为空时使用默认的 ``SessionLocal``。
    :param cancel_poll_seconds: 取消监视的轮询间隔;为 None 时不监视(测试中常用)。
    """
    handler = get_handler(job.type)
    ctx = JobContext.from_job(db, job, breaker or ProviderBreaker())
    if handler is None:
        await ctx.fail(f"Unknown job type: {ctx.type}")
        return
    set_locale(ctx.locale)
    logger.info("Starting job %s (%s) for %s #%s", ctx.job_id, ctx.type, ctx.target_type, ctx.target_id)

    runner = asyncio.ensure_future(_run_handler(handler, ctx))
    watcher = None
    if cancel_poll_seconds:
        if session_factory is None:
            from app.db.session import SessionLocal

            session_factory = SessionLocal
        watcher = asyncio.ensure_future(_watch_for_cancel(ctx.job_id, runner, session_factory, cancel_poll_seconds))
    try:
        await runner
    except JobStopped:
        await db.rollback()
        logger.info("Job %s stopped before finishing", ctx.job_id)
    except asyncio.CancelledError:
        stopped_by_user = watcher is not None and watcher.done() and not watcher.cancelled() and watcher.result()
        if not stopped_by_user:
            raise
        await db.rollback()
        logger.info("Job %s was cancelled while running", ctx.job_id)
    except Exception as exc:  # noqa: BLE001 - 处理器的任何异常都只让这条 job 失败
        logger.exception("Job %s crashed", ctx.job_id)
        await ctx.fail(str(exc) or exc.__class__.__name__)
    finally:
        if watcher is not None and not watcher.done():
            watcher.cancel()


# region 内部实现

async def _run_handler(handler: Any, ctx: JobContext) -> None:
    """执行处理器;正常返回而没有显式结束时,兜底记为成功并提交。"""
    await handler.run(ctx)
    if not ctx.finished:
        await ctx.succeed()
        await ctx.db.commit()


async def _watch_for_cancel(
    job_id: int,
    runner: "asyncio.Future[Any]",
    session_factory: Callable[[], Any],
    interval: float,
) -> bool:
    """job 被取消/删除/重置时中止正在执行的 runner;返回是否由它中止。"""
    while not runner.done():
        await asyncio.sleep(interval)
        if runner.done():
            break
        try:
            async with session_factory() as session:
                status = await session.scalar(select(Job.status).where(Job.id == job_id))
        except Exception:  # noqa: BLE001 - 查询失败就等下一轮
            continue
        if status != JobStatus.RUNNING.value:
            runner.cancel()
            return True
    return False

# endregion
