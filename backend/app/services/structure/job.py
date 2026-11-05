"""题干拆解的 job 处理器(``structure.decompose``)。

执行:取对象当前题干 → (材料小题)准备可引用的材料条件 → 调 AI 拆解并体检 → 存为待审快照。
没有业务状态需要投影:拆解进度直接看 job,结果看 ``struct_runs``。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_task import ImportPauseReason
from app.models.question_structure import StructOrigin, StructTargetType
from app.services.jobs import JobContext, JobHandler, JobStopped, register_handler

from . import service as struct_service
from . import settings as struct_settings
from .decompose import ModelNotConfigured, SharedCondition, decompose

logger = logging.getLogger(__name__)

ERROR_DISABLED = "structure_disabled"
ERROR_EMPTY_STEM = "empty_stem"


@register_handler
class DecomposeJobHandler(JobHandler):
    """把一道题(或一份材料)的题干拆成条件与设问。"""

    type = struct_service.JOB_TYPE
    target_type = None  # 题目或材料,见 job.target_type

    # region 公共接口

    async def run(self, ctx: JobContext) -> None:
        db = ctx.db
        if not await struct_settings.is_enabled(db):
            await ctx.fail("Question structure is disabled", error_code=ERROR_DISABLED)
            return
        try:
            target = await struct_service.load_target(db, ctx.target_type or "", ctx.target_id or 0)
        except Exception as exc:  # noqa: BLE001 - 对象已删除等:这条 job 失败即可
            await ctx.fail(str(exc) or "Target not found")
            return
        if not target.stem_text.strip():
            await ctx.fail("The stem is empty", error_code=ERROR_EMPTY_STEM)
            return

        from app.services.ai_resolver import resolve_provider_id

        provider_id = await resolve_provider_id(db, user_id=ctx.user_id, purpose="text")
        if provider_id is None:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        await ctx.set_progress(stage="decomposing")

        try:
            shared = await self._shared_conditions(ctx, target.stimulus_id)
            draft = await decompose(
                db,
                stem_text=target.stem_text,
                subject_id=target.subject_id,
                user_id=ctx.user_id,
                shared=shared,
            )
        except ModelNotConfigured:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        except JobStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - 按 AI 错误类别暂停或失败
            logger.exception("Structure job %s: decomposition failed", ctx.job_id)
            await ctx.handle_ai_error(exc, provider_id=provider_id)
            return

        await ctx.ai_succeeded(draft.provider_id or provider_id)
        # 先把 job 记为成功(未提交):job 若已被取消,这里直接停下,不保存结果。
        await ctx.succeed(progress={"stage": "done", "errors": draft.report.error_count}, provider_id=provider_id)
        run = await struct_service.save_draft(
            db, target, draft, origin=StructOrigin.AI.value, job_id=ctx.job_id, created_by=ctx.user_id
        )
        await db.commit()
        logger.info(
            "Structure job %s: %s #%s decomposed into run %s (%d condition(s), %d ask(s), %d error(s))",
            ctx.job_id, target.type, target.id, run.id, len(draft.elements), len(draft.asks),
            draft.report.error_count,
        )

    # endregion

    # region 内部实现

    async def _shared_conditions(self, ctx: JobContext, stimulus_id: Optional[int]) -> List[SharedCondition]:
        """小题所属材料的条件;材料还没拆过时先拆材料(存为待审),再供小题引用。"""
        if not stimulus_id:
            return []
        db: AsyncSession = ctx.db
        shared = await struct_service.shared_conditions(db, stimulus_id)
        if shared:
            return shared
        try:
            material = await struct_service.load_target(db, StructTargetType.STIMULUS.value, stimulus_id)
        except Exception:  # noqa: BLE001 - 材料已删除:小题单独拆
            return []
        if not material.stem_text.strip():
            return []
        draft = await decompose(
            db, stem_text=material.stem_text, subject_id=material.subject_id, user_id=ctx.user_id
        )
        await struct_service.save_draft(
            db, material, draft, origin=StructOrigin.AI.value, job_id=ctx.job_id, created_by=ctx.user_id
        )
        await db.commit()
        return await struct_service.shared_conditions(db, stimulus_id)

    # endregion
