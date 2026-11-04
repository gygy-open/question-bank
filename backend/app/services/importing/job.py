"""导入任务的 job 处理器(``import.extract``)。

一次导入 = 一条 ``ImportTask``(业务记录:文件、识别结果、审核与入库状态)
+ 一条 ``Job``(执行记录:排队、执行、暂停、失败)。

- 执行:读取源文件 → 选择识别方式(标签解析 / AI)→ 抽取 → 存待审核结果
  (或 ``auto_commit`` 时直接入库)。
- 投影:job 的执行状态同步到 ``import_tasks`` 原有的 status / paused_reason /
  provider_id / error_message / progress 字段,导入页面、桌面通知、各类查询
  因此无需改动。这些字段只由本处理器(经 job_service)写入。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_user import user as crud_user
from app.models.import_task import ImportMethod, ImportPauseReason, ImportTask, ImportTaskStatus
from app.models.job import Job, JobPriority, JobStatus
from app.models.user import User
from app.services import import_task_service as tasks_svc
from app.services.jobs import JobContext, JobHandler, JobStopped, job_service, register_handler

logger = logging.getLogger(__name__)

JOB_TYPE = tasks_svc.JOB_TYPE
TARGET_TYPE = tasks_svc.JOB_TARGET_TYPE

# job 执行状态 → 导入任务对外展示的状态。成功不在此列:成功后的「待审核 / 已入库」
# 是业务状态,由处理器在写入结果时一并设置。
_STATUS_MAP: Dict[JobStatus, ImportTaskStatus] = {
    JobStatus.PENDING: ImportTaskStatus.PENDING,
    JobStatus.RUNNING: ImportTaskStatus.PROCESSING,
    JobStatus.PAUSED: ImportTaskStatus.PAUSED,
    JobStatus.FAILED: ImportTaskStatus.FAILED,
    JobStatus.CANCELLED: ImportTaskStatus.CANCELLED,
}
# job 投影字段 → import_tasks 列名。
_FIELD_MAP = {
    "error": "error_message",
    "paused_reason": "paused_reason",
    "provider_id": "provider_id",
    "progress": "progress",
}


# region 入队(供 API 使用)

async def enqueue_import(db: AsyncSession, task: ImportTask) -> Job:
    """为一条导入任务创建执行 job(已 flush)。调用方负责提交。"""
    return await job_service.enqueue(
        db,
        type=JOB_TYPE,
        target_type=TARGET_TYPE,
        target_id=task.id,
        priority=JobPriority.USER,
        user_id=task.user_id,
        subject_id=task.subject_id,
        locale=task.locale,
    )


async def requeue_import(db: AsyncSession, task: ImportTask) -> Job:
    """重新识别:有 job 就放回队尾,没有(例如很早以前失败的任务)就新建。调用方负责提交。"""
    job = await job_service.latest_for_target(db, TARGET_TYPE, task.id, type=JOB_TYPE)
    if job is None:
        return await enqueue_import(db, task)
    job.locale = task.locale or job.locale
    await job_service.requeue(db, job)
    return job

# endregion


@register_handler
class ImportJobHandler(JobHandler):
    """识别一份导入文件。"""

    type = JOB_TYPE
    target_type = TARGET_TYPE

    # region 公共接口

    async def ai_purpose(self, db: AsyncSession, job: Job) -> Optional[str]:
        """标签导入不需要 AI;「自动」在读取文件前无法确定,保守地视为需要。"""
        task = await db.get(ImportTask, job.target_id) if job.target_id else None
        if task is None or tasks_svc.needs_ai(task) is False:
            return None
        return tasks_svc.purpose_of(task)

    async def project(
        self, db: AsyncSession, target_ids: Sequence[int], status: JobStatus, **values: Any
    ) -> None:
        """把执行状态写回 import_tasks,保持导入页面上的状态与 job 一致。"""
        mapped = _STATUS_MAP.get(status)
        if mapped is None:
            return
        columns: Dict[str, Any] = {"status": mapped, "updated_at": datetime.utcnow()}
        for key, column in _FIELD_MAP.items():
            if key in values:
                columns[column] = values[key]
        if status == JobStatus.CANCELLED:
            # 取消即放弃识别结果。
            columns["result_sha256"] = None
        await db.execute(
            update(ImportTask)
            .where(ImportTask.id.in_(list(target_ids)))
            .values(**columns)
            .execution_options(synchronize_session=False)
        )

    async def run(self, ctx: JobContext) -> None:
        """读取源文件、识别题目,结果存为待审核(或直接入库)。"""
        db = ctx.db
        # populate_existing:会话里可能已缓存这条记录(状态是领取前的旧值),以库里为准。
        task = await db.get(ImportTask, ctx.target_id, populate_existing=True) if ctx.target_id else None
        if task is None:
            await ctx.fail("Import task not found")
            return
        logger.info("Import task %s (%s): %s", task.id, task.file_type, task.original_filename)
        if task.subject_id is None and task.user_id:
            # 早期任务没有记录学科,沿用用户当前学科。
            user = await db.get(User, task.user_id)
            task.subject_id = user.last_active_subject_id if user else None
        await ctx.set_progress(stage="parsing")
        await self._extract(ctx, task)

    # endregion

    # region 内部实现

    async def _extract(self, ctx: JobContext, task: ImportTask) -> None:
        """摄取 → 选择识别方式 → 抽取 → 保存结果。"""
        db = ctx.db
        # 失败路径会 rollback 并使 ORM 对象过期,之后只用这里取出的普通值。
        task_id = task.id
        user_id = task.user_id
        subject_id = task.subject_id
        mode = task.mode or "extract"
        auto_commit = bool(task.auto_commit)

        try:
            source = await tasks_svc.ingest_task_source(db, task)
        except tasks_svc.SourceUnavailable as exc:
            await ctx.fail(str(exc), error_code=tasks_svc.ERROR_SOURCE_UNAVAILABLE)
            return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - 文件读不出来只让这条任务失败
            logger.exception("Import task %s: failed to read the document", task_id)
            await ctx.fail(str(exc) or exc.__class__.__name__, error_code=tasks_svc.ERROR_PARSE_FAILED)
            return

        method = _decide_method(task, source)
        provider_id: Optional[int] = None
        if method == ImportMethod.AI.value:
            from app.services.ai_resolver import resolve_provider_id

            provider_id = await resolve_provider_id(
                db, user_id=user_id, purpose=tasks_svc.purpose_of(task)  # type: ignore[arg-type]
            )
            if provider_id is None:
                await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
                return
        await ctx.set_progress(stage="extracting", method=method)

        async def on_stage(stage: str) -> None:
            await ctx.set_progress(stage=stage, method=method)

        from app.services.doc_processor import doc_processor

        try:
            extraction = await doc_processor.extractor_for(method).extract(
                source.markdown,
                db,
                image_data=source.image_data,
                filename=source.filename,
                mode=mode,
                subject_id=subject_id,
                user_id=user_id,
                on_stage=on_stage,
            )
        except (asyncio.CancelledError, JobStopped):
            # 识别途中任务被取消:交给 runner 收尾,不当作识别失败。
            raise
        except Exception as exc:  # noqa: BLE001 - 按错误类别暂停或失败
            if method == ImportMethod.AI.value:
                logger.exception("Import task %s: AI extraction failed", task_id)
                await ctx.handle_ai_error(exc, provider_id=provider_id, method=method)
            else:
                logger.exception("Import task %s: structured parsing failed", task_id)
                await ctx.fail(str(exc), error_code=tasks_svc.ERROR_PARSE_FAILED, method=method)
            return

        await ctx.ai_succeeded(provider_id)

        count = len(extraction.questions or [])
        if count == 0:
            await ctx.fail(
                "No questions were found in the document",
                error_code=tasks_svc.ERROR_NO_QUESTIONS,
                method=method,
            )
            return

        if auto_commit:
            await self._commit_directly(ctx, task, extraction, method=method, count=count)
            return

        payload = tasks_svc.review_payload(task, source, extraction, method=method)
        result_sha256 = await asyncio.to_thread(tasks_svc.save_result, payload)
        progress = dict(stage="ready", method=method, count=count)
        await ctx.succeed(progress=progress, provider_id=provider_id)
        await db.execute(
            update(ImportTask)
            .where(ImportTask.id == task_id)
            .values(
                status=ImportTaskStatus.REVIEW_READY,
                result_sha256=result_sha256,
                provider_id=provider_id,
                error_message=None,
                progress=tasks_svc.dump_progress(**progress),
                updated_at=datetime.utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        logger.info("Import task %s ready for review: %d question(s)", task_id, count)

    async def _commit_directly(
        self, ctx: JobContext, task: ImportTask, extraction: Any, *, method: str, count: int
    ) -> None:
        """识别后直接入库(跳过审核)。"""
        from app.services.paper_import_service import commit_extracted_paper_import

        db = ctx.db
        task_id = task.id
        # 查重要读用户的学科成员关系,异步会话里必须预加载。
        user = await crud_user.get_with_memberships(db, id=task.user_id) if task.user_id else None
        if user is None or task.subject_id is None:
            await ctx.fail("Import task requires a user and a subject", method=method)
            return
        progress = dict(stage="done", method=method, count=count)
        # 先把 job 记为成功(未提交):若 job 已被取消,这里直接停下,不会入库。
        await ctx.succeed(progress=progress)
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
        except Exception as exc:  # noqa: BLE001 - 入库失败只让这条任务失败
            logger.exception("Import task %s: failed to save questions", task_id)
            await ctx.fail(str(exc) or exc.__class__.__name__, method=method)
            return
        task.progress = tasks_svc.dump_progress(**progress)
        task.updated_at = datetime.utcnow()
        await db.commit()
        # 直接入库也是入库:按学科开关自动排队拆解题干(失败不影响导入)。
        from app.services.structure.service import after_questions_saved

        await after_questions_saved(db, report.created_questions, user_id=user.id)
        logger.info(
            "Import task %s completed. Saved %d questions, %d skipped.",
            task_id, len(report.created_questions), len(report.skipped),
        )

    # endregion


def _decide_method(task: ImportTask, source: tasks_svc.IngestedSource) -> str:
    """「自动」方式:文档里有结构化标签就按标签解析,否则交给 AI。"""
    from app.services.structured_parser import has_structured_tags

    method = tasks_svc.method_of(task)
    if method != ImportMethod.AUTO.value:
        return method
    return ImportMethod.STRUCTURED.value if has_structured_tags(source.markdown) else ImportMethod.AI.value
