"""题干结构化能力 —— 写路径。

读路径(查看拆解、类型树、同结构题、审核队列)与题目域一致,刻意不放进能力层:端点
直接调用 ``app.services.structure.service``,MCP 另有同等门禁的只读工具。

MCP 暴露范围:``structure.decompose``、``structure.save``(只能存为待审);审核、类型树的
修改、存量回填只在站内使用(见 ``app/mcp_server/tools.py`` 的 EXCLUDED_CAPABILITIES)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.core import permissions
from app.core.api_errors import ErrorCode
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible
from app.models.job import JobPriority
from app.models.question_structure import StructRun, StructTargetType, StructType
from app.services.activity_logger import log_activity
from app.services.structure import service as struct_service
from app.services.structure import settings as struct_settings
from app.services.structure import types as type_svc

from .base import Authz, Capability, Scope
from .context import ExecutionContext, Surface
from .errors import Forbidden, Invalid, NotFound
from .registry import register

TargetTypeLiteral = Literal["question", "stimulus"]
# 一次批量拆解 / 审核的上限。
_BATCH_MAX = 500
_BACKFILL_MAX = 5000


# region 输入模型

class StructureDecomposeInput(BaseModel):
    """Queue decomposition of question stems or materials."""

    target_type: TargetTypeLiteral = Field("question", description="question (default) or stimulus (material).")
    target_ids: List[int] = Field(..., min_length=1, max_length=_BATCH_MAX, description="IDs to decompose.")


class StructureItemInput(BaseModel):
    """One condition or ask of a decomposition."""

    content: str = Field(..., description="One self-contained statement, math in $...$.")
    source: Optional[str] = Field(None, description="Exact quote of the stem this item comes from.")
    span_start: Optional[int] = Field(None, description="Start offset in the run's stem_text.")
    span_end: Optional[int] = Field(None, description="End offset (exclusive) in the run's stem_text.")
    type_id: Optional[int] = Field(None, description="Structure type ID (see list_structure_types).")
    type_hint: Optional[str] = Field(None, max_length=255, description="Free-text category when no type fits.")
    facet: Optional[Literal["quant", "qual", "proc", "form"]] = Field(None, description="Conditions only.")
    ref_element_id: Optional[int] = Field(None, description="Conditions only: shared material condition ID.")
    depends_on: List[int] = Field(default_factory=list, description="Asks only: 0-based indices of conditions.")


class StructureSaveInput(BaseModel):
    """An edited decomposition, saved as a new draft."""

    target_type: TargetTypeLiteral = "question"
    target_id: int
    base_run_id: Optional[int] = Field(None, description="The run this edit started from, if any.")
    elements: List[StructureItemInput] = Field(default_factory=list, description="Conditions.")
    asks: List[StructureItemInput] = Field(default_factory=list, description="Asks.")
    accept: bool = Field(False, description="Accept immediately after saving (not available via MCP).")


class StructureReviewInput(BaseModel):
    """Accept or reject draft decompositions."""

    run_ids: List[int] = Field(..., min_length=1, max_length=_BATCH_MAX)
    action: Literal["accept", "reject"]


class StructureBackfillInput(BaseModel):
    """Queue decomposition for undecomposed questions of a subject."""

    subject_id: int
    limit: int = Field(500, ge=1, le=_BACKFILL_MAX)


class StructTypeCreateInput(BaseModel):
    subject_id: int
    name: str = Field(..., min_length=1, max_length=128)
    kind: Optional[Literal["condition", "ask"]] = None
    parent_id: Optional[int] = None
    code: Optional[str] = Field(None, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    definition: Optional[str] = None
    examples: Optional[List[Dict[str, Any]]] = None
    status: Literal["candidate", "active", "deprecated"] = "active"
    sort_order: Optional[int] = None


class StructTypeUpdateInput(BaseModel):
    id: int
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    parent_id: Optional[int] = None
    move: bool = Field(False, description="Apply parent_id (null moves to root).")
    definition: Optional[str] = None
    examples: Optional[List[Dict[str, Any]]] = None
    status: Optional[Literal["candidate", "active", "deprecated"]] = None
    sort_order: Optional[int] = None


class StructTypeIdInput(BaseModel):
    id: int


class StructTypeMergeInput(BaseModel):
    source_id: int
    target_id: int


class StructTypeImportInput(BaseModel):
    subject_id: int
    items: List[Dict[str, Any]] = Field(..., min_length=1, max_length=5000)

# endregion


# region 拆解

@register
class DecomposeStructure(Capability[StructureDecomposeInput, dict]):
    name = "structure.decompose"
    description = (
        "Queue AI decomposition of question stems (or materials) into conditions and asks. "
        "Only the stem is used, never the answer. Results are saved as drafts for review; "
        "read them with get_question_structure."
    )
    input_model = StructureDecomposeInput
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def authorize(self, ctx: ExecutionContext, inp: StructureDecomposeInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)

    async def execute(self, ctx: ExecutionContext, inp: StructureDecomposeInput, target: Any) -> dict:
        from app.core.locale import get_locale

        queued: List[int] = []
        skipped: List[int] = []
        job_ids: List[int] = []
        for target_id in dict.fromkeys(inp.target_ids):
            try:
                found = await struct_service.load_target(ctx.db, inp.target_type, target_id)
            except NotFound:
                skipped.append(target_id)
                continue
            # 逐条判权:看不到或无编辑权的跳过,不让整批失败。
            if not _can_edit(ctx, found):
                skipped.append(target_id)
                continue
            job = await struct_service.enqueue_decompose(
                ctx.db, found.type, found.id,
                priority=JobPriority.USER, user_id=ctx.actor.id, subject_id=found.subject_id, locale=get_locale(),
            )
            queued.append(target_id)
            job_ids.append(job.id)
        await ctx.db.commit()
        return {"queued": queued, "skipped": skipped, "job_ids": job_ids}


@register
class SaveStructure(Capability[StructureSaveInput, dict]):
    name = "structure.save"
    description = (
        "Save an edited decomposition of a question stem as a new draft (the AI result is kept for comparison). "
        "Each condition states one thing; asks list the conditions they depend on by index."
    )
    input_model = StructureSaveInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: StructureSaveInput) -> struct_service.Target:
        found = await struct_service.load_target(ctx.db, inp.target_type, inp.target_id)
        if not is_question_visible(found.obj, ctx.actor):
            raise NotFound("Not found", ErrorCode.STRUCTURE_TARGET_NOT_FOUND)
        return found

    async def authorize(self, ctx: ExecutionContext, inp: StructureSaveInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)
        await super().authorize(ctx, inp, target)

    async def execute(self, ctx: ExecutionContext, inp: StructureSaveInput, target: struct_service.Target) -> dict:
        base = await struct_service.get_run(ctx.db, inp.base_run_id) if inp.base_run_id else None
        if base is not None and (base.target_type, base.target_id) != (target.type, target.id):
            raise Invalid("Base run belongs to another target", ErrorCode.STRUCTURE_INVALID_ITEM)
        run = await struct_service.save_human(
            ctx.db,
            target,
            elements=[item.model_dump() for item in inp.elements],
            asks=[item.model_dump() for item in inp.asks],
            user_id=ctx.actor.id,
            base_run=base,
        )
        # 外部 AI 客户端只能提交待审结果,采纳必须由人在站内完成。
        if inp.accept and ctx.surface != Surface.MCP:
            await struct_service.review(ctx.db, run, accept=True, reviewer_id=ctx.actor.id)
        await log_activity(
            ctx.db, ctx.actor.id, action="structure_save", resource_type=target.type, resource_id=target.id,
            details={"run_id": run.id, "accepted": run.state == "accepted"},
        )
        await ctx.db.commit()
        return await struct_service.structure_view(ctx.db, target)


@register
class ReviewStructure(Capability[StructureReviewInput, dict]):
    name = "structure.review"
    description = "Accept or reject draft decompositions. Accepting replaces the previously accepted one."
    input_model = StructureReviewInput
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def execute(self, ctx: ExecutionContext, inp: StructureReviewInput, target: Any) -> dict:
        updated: List[int] = []
        skipped: List[int] = []
        for run_id in dict.fromkeys(inp.run_ids):
            run = await ctx.db.get(StructRun, run_id)
            if run is None or run.state != "draft":
                skipped.append(run_id)
                continue
            try:
                found = await struct_service.load_target(ctx.db, run.target_type, run.target_id)
            except NotFound:
                skipped.append(run_id)
                continue
            if not _can_edit(ctx, found):
                skipped.append(run_id)
                continue
            await struct_service.review(ctx.db, run, accept=inp.action == "accept", reviewer_id=ctx.actor.id)
            updated.append(run_id)
        if updated:
            await log_activity(
                ctx.db, ctx.actor.id, action=f"structure_{inp.action}", resource_type="struct_run",
                resource_id=updated[0], details={"run_ids": updated},
            )
        await ctx.db.commit()
        return {"updated": updated, "skipped": skipped}


@register
class BackfillStructure(Capability[StructureBackfillInput, dict]):
    name = "structure.backfill"
    description = "Queue low-priority decomposition for questions of a subject that have no decomposition yet."
    input_model = StructureBackfillInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_SUBJECT
    scope = Scope.SUBJECT
    mutating = True

    async def authorize(self, ctx: ExecutionContext, inp: StructureBackfillInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)
        await super().authorize(ctx, inp, target)

    async def execute(self, ctx: ExecutionContext, inp: StructureBackfillInput, target: Any) -> dict:
        from app.core.locale import get_locale

        ids = await struct_service.backfill_candidates(ctx.db, inp.subject_id, limit=inp.limit)
        for question_id in ids:
            await struct_service.enqueue_decompose(
                ctx.db, StructTargetType.QUESTION.value, question_id,
                priority=JobPriority.BACKFILL, user_id=ctx.actor.id, subject_id=inp.subject_id, locale=get_locale(),
            )
        await ctx.db.commit()
        return {"queued": len(ids)}

# endregion


# region 元素类型树

class _TypeCapability(Capability):
    """类型树的修改:学科内有「编辑知识点 / 标签」权限的人可以维护。"""

    authz = Authz.PERMISSION
    permission = Permission.EDIT_TAXONOMY
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: Any) -> Optional[StructType]:
        type_id = getattr(inp, "id", None) or getattr(inp, "source_id", None)
        return await type_svc.get_type(ctx.db, type_id) if type_id else None


@register
class CreateStructType(_TypeCapability):
    name = "struct_type.create"
    description = "Create a structure type (a category of stem conditions or asks) in a subject."
    input_model = StructTypeCreateInput

    async def execute(self, ctx: ExecutionContext, inp: StructTypeCreateInput, target: Any) -> StructType:
        await type_svc.ensure_roots(ctx.db, inp.subject_id)
        return await type_svc.create_type(
            ctx.db,
            subject_id=inp.subject_id,
            name=inp.name,
            kind=inp.kind,
            parent_id=inp.parent_id,
            code=inp.code,
            definition=inp.definition,
            examples=inp.examples,
            status=inp.status,
            sort_order=inp.sort_order,
            created_by=ctx.actor.id,
        )


@register
class UpdateStructType(_TypeCapability):
    name = "struct_type.update"
    description = "Rename, move, re-describe or change the status of a structure type."
    input_model = StructTypeUpdateInput

    async def execute(self, ctx: ExecutionContext, inp: StructTypeUpdateInput, target: StructType) -> StructType:
        changes = inp.model_dump(exclude_unset=True, exclude={"id", "move"})
        if not inp.move:
            changes.pop("parent_id", None)
        elif "parent_id" not in changes:
            changes["parent_id"] = None
        return await type_svc.update_type(ctx.db, target, changes)


@register
class DeleteStructType(_TypeCapability):
    name = "struct_type.delete"
    description = "Delete an unused structure type without children."
    input_model = StructTypeIdInput

    async def execute(self, ctx: ExecutionContext, inp: StructTypeIdInput, target: StructType) -> None:
        await type_svc.delete_type(ctx.db, target)


@register
class MergeStructType(_TypeCapability):
    name = "struct_type.merge"
    description = "Merge one structure type into another; references and children move to the target."
    input_model = StructTypeMergeInput

    async def execute(self, ctx: ExecutionContext, inp: StructTypeMergeInput, target: StructType) -> StructType:
        destination = await type_svc.get_type(ctx.db, inp.target_id)
        return await type_svc.merge_types(ctx.db, target, destination)


@register
class ImportStructTypes(_TypeCapability):
    name = "struct_type.import"
    description = "Import structure types by code (create or update)."
    input_model = StructTypeImportInput

    async def execute(self, ctx: ExecutionContext, inp: StructTypeImportInput, target: Any) -> dict:
        await type_svc.ensure_roots(ctx.db, inp.subject_id)
        return await type_svc.import_types(ctx.db, inp.subject_id, inp.items, created_by=ctx.actor.id)

# endregion


def _can_edit(ctx: ExecutionContext, target: struct_service.Target) -> bool:
    """对象对当前用户可见,且用户在其学科有编辑题目的权限。"""
    return is_question_visible(target.obj, ctx.actor) and permissions.can(
        ctx.actor, Permission.EDIT_QUESTION, subject_id=target.subject_id
    )
