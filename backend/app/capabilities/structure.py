"""题干结构化能力 —— 写路径。

读路径(查看拆解、类型树、同结构题、审核队列)与题目域一致,刻意不放进能力层:端点
直接调用 ``app.services.structure.service``,MCP 另有同等门禁的只读工具。

MCP 暴露范围(规格 §12.3 N5,2026-11-05 修订):外部 Agent 可以拆解、保存(只能存为待审)、
生成变式 / 整组替换 / 拼装命题、拆解解答,并维护类型树与归纳;**采纳**(``structure.review``、
``solution.review``)与存量回填只在站内使用(见 ``app/mcp_server/tools.py`` 的 EXCLUDED_CAPABILITIES)。
Agent 发起的写入记为 MCP 渠道:拆解来源为 agent,生成的题目 ``created_via='mcp'``。
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core import permissions
from app.core.api_errors import ErrorCode
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible
from app.models.job import JobPriority
from app.models.question_structure import StructOrigin, StructRun, StructTargetType, StructType, StructTypeCandidate
from app.services.activity_logger import log_activity
from app.services.structure import compose as compose_svc
from app.services.structure import induce as induce_svc
from app.services.structure import solution as solution_svc
from app.services.structure import variant as variant_svc
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


class StructureParamInput(BaseModel):
    """A replaceable value (parameter slot) inside one condition or ask."""

    owner: Literal["element", "ask"] = Field(..., description="Whether the parameter belongs to a condition or an ask.")
    owner_index: int = Field(..., ge=0, description="0-based index of the owning condition / ask in this save.")
    name: str = Field(..., min_length=1, max_length=64, description="Short label, e.g. a or constant term.")
    value: str = Field(..., min_length=1, description="The value exactly as written in the stem (LaTeX without $).")
    slot_kind: Literal["numeric", "symbolic", "point", "interval", "expression"] = "numeric"
    span_start: Optional[int] = Field(None, description="Start offset in the run's stem_text.")
    span_end: Optional[int] = Field(None, description="End offset (exclusive) in the run's stem_text.")
    occurrence: int = Field(1, ge=1, description="Which standalone occurrence inside the owner's source (when no span).")
    domain: Optional[Dict[str, Any]] = Field(
        None, description="Allowed values: {min, max, integer, values, exclude, note}."
    )
    domain_confirmed: bool = Field(False, description="Teacher confirmed the domain (ignored via MCP; only teachers confirm).")
    replaceable: bool = True


class StructureGroupInput(BaseModel):
    """Conditions treated as one unit that can be replaced together."""

    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    replaceable: bool = True
    element_indices: List[int] = Field(..., min_length=2, description="0-based indices of conditions in this save.")


class StructureSaveInput(BaseModel):
    """An edited decomposition, saved as a new draft."""

    target_type: TargetTypeLiteral = "question"
    target_id: int
    base_run_id: Optional[int] = Field(None, description="The run this edit started from, if any.")
    elements: List[StructureItemInput] = Field(default_factory=list, description="Conditions.")
    asks: List[StructureItemInput] = Field(default_factory=list, description="Asks.")
    params: List[StructureParamInput] = Field(default_factory=list, description="Parameter slots.")
    groups: List[StructureGroupInput] = Field(default_factory=list, description="Element groups.")
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
    kind: Optional[Literal["condition", "ask", "method"]] = None
    parent_id: Optional[int] = None
    code: Optional[str] = Field(None, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$")
    definition: Optional[str] = None
    examples: Optional[List[Dict[str, Any]]] = None
    status: Literal["candidate", "active", "deprecated"] = "active"
    sort_order: Optional[int] = None
    weight: Optional[float] = Field(None, gt=0, le=100, description="Thinking-load weight (method types).")


class StructTypeUpdateInput(BaseModel):
    id: int
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    parent_id: Optional[int] = None
    move: bool = Field(False, description="Apply parent_id (null moves to root).")
    definition: Optional[str] = None
    examples: Optional[List[Dict[str, Any]]] = None
    status: Optional[Literal["candidate", "active", "deprecated"]] = None
    sort_order: Optional[int] = None
    weight: Optional[float] = Field(None, gt=0, le=100)
    knowledge_point_ids: Optional[List[int]] = Field(None, description="Replace the mapped knowledge points.")


class StructTypeRead(BaseModel):
    """A structure type node (output)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    parent_id: Optional[int] = None
    kind: str
    code: str
    name: str
    definition: Optional[str] = None
    status: str
    sort_order: int
    weight: float = 1.0


class StructTypeIdInput(BaseModel):
    id: int


class StructTypeMergeInput(BaseModel):
    source_id: int
    target_id: int


class StructTypeImportInput(BaseModel):
    subject_id: int
    items: List[Dict[str, Any]] = Field(..., min_length=1, max_length=5000)


class StructureVariantValue(BaseModel):
    param_id: int
    value: str = Field(..., min_length=1, max_length=500)


class StructureVariantInput(BaseModel):
    """Generate a variant question by changing parameter values."""

    question_id: int
    run_id: Optional[int] = Field(None, description="Decomposition to use; defaults to the accepted one.")
    values: List[StructureVariantValue] = Field(default_factory=list, max_length=50)
    auto_param_ids: List[int] = Field(
        default_factory=list, max_length=50, description="Parameters whose new value AI picks within the confirmed domain."
    )


class SolutionDecomposeInput(BaseModel):
    """Queue AI decomposition of solutions into steps."""

    question_ids: List[int] = Field(..., min_length=1, max_length=_BATCH_MAX)
    solution_no: int = Field(1, ge=1, le=9, description="Which solution method (1 = first).")


class SolutionMisconceptionInput(BaseModel):
    description: str = Field(..., min_length=1)
    source: Literal["distractor", "response"] = "distractor"


class SolutionStepInput(BaseModel):
    """One solution step; conditions / asks are IDs from the accepted stem decomposition."""

    goal: str = Field(..., min_length=1)
    result: Optional[str] = None
    method_type_id: Optional[int] = None
    method_hint: Optional[str] = Field(None, max_length=255)
    is_key: bool = False
    uses_elements: List[int] = Field(default_factory=list)
    uses_asks: List[int] = Field(default_factory=list)
    uses_steps: List[int] = Field(default_factory=list, description="0-based indices of earlier steps.")
    answers: List[int] = Field(default_factory=list, description="Ask IDs this step answers.")
    misconceptions: List[SolutionMisconceptionInput] = Field(default_factory=list)


class SolutionSaveInput(BaseModel):
    """An edited solution decomposition, saved as a new draft."""

    question_id: int
    solution_no: int = Field(1, ge=1, le=9)
    steps: List[SolutionStepInput] = Field(..., min_length=1, max_length=60)
    accept: bool = Field(False, description="Accept immediately after saving (not available via MCP).")


class SolutionReviewInput(BaseModel):
    run_ids: List[int] = Field(..., min_length=1, max_length=_BATCH_MAX)
    action: Literal["accept", "reject"]


class StructureComposeInput(BaseModel):
    """Compose a new question from conditions / asks / groups of accepted decompositions (may span questions)."""

    element_ids: List[int] = Field(default_factory=list, max_length=30)
    ask_ids: List[int] = Field(default_factory=list, max_length=10)
    group_ids: List[int] = Field(default_factory=list, max_length=10)
    q_type: Literal["single_choice", "multiple_choice", "true_false", "fill_in_the_blank", "free_response"] = "free_response"
    note: Optional[str] = Field(None, max_length=1000)


class StructureGroupReplaceInput(BaseModel):
    """Replace an element group with another group of the same condition types."""

    group_id: int
    source_group_id: int


class StructTypeInduceInput(BaseModel):
    subject_id: int


class StructCandidateAcceptInput(BaseModel):
    id: int
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    parent_id: Optional[int] = None
    definition: Optional[str] = None


class StructCandidateMergeInput(BaseModel):
    id: int
    type_id: int


class StructCandidateIdInput(BaseModel):
    id: int

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
            # 取值范围只能由站内老师确认;外部 Agent 提交的范围一律待确认。
            params=[
                {**item.model_dump(), "domain_confirmed": item.domain_confirmed and ctx.surface != Surface.MCP}
                for item in inp.params
            ],
            groups=[item.model_dump() for item in inp.groups],
            user_id=ctx.actor.id,
            base_run=base,
            origin=StructOrigin.AGENT.value if ctx.surface == Surface.MCP else StructOrigin.HUMAN.value,
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
            weight=inp.weight,
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


# region 变式(参数槽)

@register
class GenerateVariant(Capability[StructureVariantInput, dict]):
    name = "structure.variant"
    description = (
        "Queue generation of a variant question: replace parameter values by position, let AI re-solve and "
        "verify it, then save it as a draft question linked with variant_of."
    )
    input_model = StructureVariantInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: StructureVariantInput) -> struct_service.Target:
        found = await struct_service.load_target(ctx.db, StructTargetType.QUESTION.value, inp.question_id)
        if not is_question_visible(found.obj, ctx.actor):
            raise NotFound("Not found", ErrorCode.STRUCTURE_TARGET_NOT_FOUND)
        return found

    async def authorize(self, ctx: ExecutionContext, inp: StructureVariantInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)
        await super().authorize(ctx, inp, target)

    async def execute(self, ctx: ExecutionContext, inp: StructureVariantInput, target: struct_service.Target) -> dict:
        from app.core.locale import get_locale

        plan = await variant_svc.plan_variant(
            ctx.db,
            target.obj,
            run_id=inp.run_id,
            values={item.param_id: item.value for item in inp.values},
            auto=inp.auto_param_ids,
        )
        job = await variant_svc.enqueue(ctx.db, plan, user_id=ctx.actor.id, locale=get_locale())
        await ctx.db.commit()
        return {"job_id": job.id}

# endregion


# region 解答结构(三期)

@register
class DecomposeSolutions(Capability[SolutionDecomposeInput, dict]):
    name = "solution.decompose"
    description = "Queue AI decomposition of question solutions into steps (needs an accepted stem decomposition)."
    input_model = SolutionDecomposeInput
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def authorize(self, ctx: ExecutionContext, inp: SolutionDecomposeInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)

    async def execute(self, ctx: ExecutionContext, inp: SolutionDecomposeInput, target: Any) -> dict:
        from app.core.locale import get_locale
        from app.models.question import Question

        queued: List[int] = []
        skipped: List[int] = []
        job_ids: List[int] = []
        for question_id in dict.fromkeys(inp.question_ids):
            question = await ctx.db.get(Question, question_id)
            found = None
            if question is not None and question.deleted_at is None:
                found = struct_service.Target(
                    type="question", id=question.id, subject_id=question.subject_id,
                    revision=question.content_revision or 1, stem_text="", stimulus_id=question.stimulus_id, obj=question,
                )
            if found is None or not _can_edit(ctx, found):
                skipped.append(question_id)
                continue
            try:
                await solution_svc.stem_context(ctx.db, question)
            except Invalid:
                skipped.append(question_id)
                continue
            job = await solution_svc.enqueue(
                ctx.db, question, solution_no=inp.solution_no, user_id=ctx.actor.id, locale=get_locale()
            )
            queued.append(question_id)
            job_ids.append(job.id)
        await ctx.db.commit()
        return {"queued": queued, "skipped": skipped, "job_ids": job_ids}


@register
class SaveSolution(Capability[SolutionSaveInput, dict]):
    name = "solution.save"
    description = "Save an edited solution decomposition as a new draft."
    input_model = SolutionSaveInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: SolutionSaveInput) -> Any:
        found = await struct_service.load_target(ctx.db, StructTargetType.QUESTION.value, inp.question_id)
        if not is_question_visible(found.obj, ctx.actor):
            raise NotFound("Not found", ErrorCode.STRUCTURE_TARGET_NOT_FOUND)
        return found

    async def authorize(self, ctx: ExecutionContext, inp: SolutionSaveInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)
        await super().authorize(ctx, inp, target)

    async def execute(self, ctx: ExecutionContext, inp: SolutionSaveInput, target: Any) -> dict:
        run = await solution_svc.save_human(
            ctx.db,
            target.obj,
            steps=[step.model_dump() for step in inp.steps],
            solution_no=inp.solution_no,
            user_id=ctx.actor.id,
            origin=StructOrigin.AGENT.value if ctx.surface == Surface.MCP else StructOrigin.HUMAN.value,
        )
        if inp.accept and ctx.surface != Surface.MCP:
            await solution_svc.review(ctx.db, run, accept=True, reviewer_id=ctx.actor.id)
        await log_activity(
            ctx.db, ctx.actor.id, action="solution_save", resource_type="question", resource_id=target.id,
            details={"run_id": run.id, "accepted": run.state == "accepted"},
        )
        await ctx.db.commit()
        await ctx.db.refresh(target.obj)
        return await solution_svc.solution_view(ctx.db, target.obj)


@register
class ReviewSolutions(Capability[SolutionReviewInput, dict]):
    name = "solution.review"
    description = "Accept or reject draft solution decompositions."
    input_model = SolutionReviewInput
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def execute(self, ctx: ExecutionContext, inp: SolutionReviewInput, target: Any) -> dict:
        from app.models.solution_structure import SolutionRun

        updated: List[int] = []
        skipped: List[int] = []
        for run_id in dict.fromkeys(inp.run_ids):
            run = await ctx.db.get(SolutionRun, run_id)
            if run is None or run.state != "draft":
                skipped.append(run_id)
                continue
            try:
                found = await struct_service.load_target(ctx.db, StructTargetType.QUESTION.value, run.question_id)
            except NotFound:
                skipped.append(run_id)
                continue
            if not _can_edit(ctx, found):
                skipped.append(run_id)
                continue
            await solution_svc.review(ctx.db, run, accept=inp.action == "accept", reviewer_id=ctx.actor.id)
            updated.append(run_id)
        await ctx.db.commit()
        return {"updated": updated, "skipped": skipped}

# endregion


# region 元素重组与命题(四期)

@register
class ComposeQuestion(Capability[StructureComposeInput, dict]):
    name = "structure.compose"
    description = "Queue AI composition of a new draft question from chosen conditions and asks."
    input_model = StructureComposeInput
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def authorize(self, ctx: ExecutionContext, inp: StructureComposeInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)

    async def execute(self, ctx: ExecutionContext, inp: StructureComposeInput, target: Any) -> dict:
        from app.core.locale import get_locale

        _, _, question_ids, subject_id = await compose_svc.load_items(
            ctx.db, ctx.actor, element_ids=inp.element_ids, ask_ids=inp.ask_ids, group_ids=inp.group_ids
        )
        if not permissions.can(ctx.actor, Permission.EDIT_QUESTION, subject_id=subject_id):
            raise Forbidden("The user doesn't have enough privileges", ErrorCode.AUTH_FORBIDDEN)
        job = await compose_svc.enqueue(
            ctx.db, payload={"mode": "compose", **inp.model_dump()}, subject_id=subject_id,
            user_id=ctx.actor.id, locale=get_locale(),
        )
        await ctx.db.commit()
        return {"job_id": job.id, "source_question_ids": question_ids}


@register
class ReplaceGroup(Capability[StructureGroupReplaceInput, dict]):
    name = "structure.group_replace"
    description = "Queue a variant that replaces an element group with a same-type group from another question."
    input_model = StructureGroupReplaceInput
    authz = Authz.CUSTOM
    scope = Scope.SUBJECT
    mutating = True

    async def authorize(self, ctx: ExecutionContext, inp: StructureGroupReplaceInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)

    async def execute(self, ctx: ExecutionContext, inp: StructureGroupReplaceInput, target: Any) -> dict:
        from app.core.locale import get_locale

        question, *_ = await compose_svc.load_group_pair(ctx.db, ctx.actor, inp.group_id, inp.source_group_id)
        if not permissions.can(ctx.actor, Permission.EDIT_QUESTION, subject_id=question.subject_id):
            raise Forbidden("The user doesn't have enough privileges", ErrorCode.AUTH_FORBIDDEN)
        job = await compose_svc.enqueue(
            ctx.db, payload={"mode": "group", **inp.model_dump()}, subject_id=question.subject_id,
            user_id=ctx.actor.id, locale=get_locale(),
        )
        await ctx.db.commit()
        return {"job_id": job.id}

# endregion


# region 元素归纳(二期)

@register
class InduceStructTypes(Capability[StructTypeInduceInput, dict]):
    name = "struct_type.induce"
    description = "Queue AI grouping of unclassified conditions and asks into candidate structure types."
    input_model = StructTypeInduceInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_SUBJECT
    scope = Scope.SUBJECT
    mutating = True

    async def authorize(self, ctx: ExecutionContext, inp: StructTypeInduceInput, target: Any) -> None:
        if not await struct_settings.is_enabled(ctx.db):
            raise Forbidden("Question structure is disabled", ErrorCode.STRUCTURE_DISABLED)
        await super().authorize(ctx, inp, target)

    async def execute(self, ctx: ExecutionContext, inp: StructTypeInduceInput, target: Any) -> dict:
        from app.core.locale import get_locale

        counts = await induce_svc.unclassified_counts(ctx.db, inp.subject_id)
        if max(counts.values()) < induce_svc.MIN_ITEMS:
            raise Invalid(
                "Not enough unclassified items", ErrorCode.STRUCTURE_INDUCE_NOT_ENOUGH_DATA,
                {"min": induce_svc.MIN_ITEMS},
            )
        job = await induce_svc.enqueue(ctx.db, inp.subject_id, user_id=ctx.actor.id, locale=get_locale())
        await ctx.db.commit()
        return {"job_id": job.id, "unclassified": counts}


class _CandidateCapability(Capability):
    """候选的确认:与类型树维护同权限(学科内「编辑知识点 / 标签」)。"""

    authz = Authz.PERMISSION
    permission = Permission.EDIT_TAXONOMY
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: Any) -> StructTypeCandidate:
        return await induce_svc.get_candidate(ctx.db, inp.id)


@register
class AcceptStructCandidate(_CandidateCapability):
    name = "struct_type.candidate.accept"
    description = "Create a structure type from an induction candidate and classify its items."
    input_model = StructCandidateAcceptInput

    async def execute(self, ctx: ExecutionContext, inp: StructCandidateAcceptInput, target: StructTypeCandidate) -> StructType:
        return await induce_svc.accept_candidate(
            ctx.db, target, name=inp.name, parent_id=inp.parent_id, definition=inp.definition, user_id=ctx.actor.id
        )


@register
class MergeStructCandidate(_CandidateCapability):
    name = "struct_type.candidate.merge"
    description = "Classify the items of an induction candidate into an existing structure type."
    input_model = StructCandidateMergeInput

    async def execute(self, ctx: ExecutionContext, inp: StructCandidateMergeInput, target: StructTypeCandidate) -> StructType:
        return await induce_svc.merge_candidate(ctx.db, target, type_id=inp.type_id, user_id=ctx.actor.id)


@register
class IgnoreStructCandidate(_CandidateCapability):
    name = "struct_type.candidate.ignore"
    description = "Dismiss an induction candidate; its items stay unclassified and are not induced again."
    input_model = StructCandidateIdInput

    async def execute(self, ctx: ExecutionContext, inp: StructCandidateIdInput, target: StructTypeCandidate) -> None:
        await induce_svc.ignore_candidate(ctx.db, target, user_id=ctx.actor.id)

# endregion


def _can_edit(ctx: ExecutionContext, target: struct_service.Target) -> bool:
    """对象对当前用户可见,且用户在其学科有编辑题目的权限。"""
    return is_question_visible(target.obj, ctx.actor) and permissions.can(
        ctx.actor, Permission.EDIT_QUESTION, subject_id=target.subject_id
    )
