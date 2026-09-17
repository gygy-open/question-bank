"""整卷导入能力:一次确认同时产出题库题目与可复用稿件。

鉴权与组稿写路径保持一致(学科作用域的 EDIT_QUESTION):本能力既建题又建稿,
两个域在同一学科下要求同一权限,故一次判权即可。

刻意不复用 `question.batch_create`:那条能力是 `Authz.NONE`,且在建题前就 commit 了
ImportTask,无法与建稿收进同一事务。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app import crud
from app.core.permissions import Permission
from app.models.composition import ScopeType
from app.models.question import QuestionStatus
from app.schemas.paper_import import (
    PaperImportCommitResponse,
    PaperImportPreviewResponse,
)

from .base import Authz, Capability, Scope
from .context import ExecutionContext
from .errors import NotFound, Unprocessable
from .registry import register


class PaperImportScopeInput(BaseModel):
    subject_id: int
    scope_type: ScopeType
    owner_id: Optional[int] = None


class PaperImportPreviewInput(PaperImportScopeInput):
    questions: List[Dict[str, Any]] = Field(default_factory=list)
    outline: List[Dict[str, Any]] = Field(default_factory=list)


class PaperImportCommitInput(PaperImportScopeInput):
    questions: List[Dict[str, Any]] = Field(default_factory=list)
    outline: List[Dict[str, Any]] = Field(default_factory=list)
    save_as_composition: bool = False
    title: Optional[str] = None
    folder_id: Optional[int] = None
    renumber: bool = False
    proceed_with_partial: bool = False
    status: QuestionStatus = QuestionStatus.PENDING
    filename: Optional[str] = None
    file_path: Optional[str] = None
    content_sha256: Optional[str] = None
    idempotency_key: Optional[str] = None


async def _ensure_subject(ctx: ExecutionContext, subject_id: int) -> None:
    if not await crud.subject.get(ctx.db, id=subject_id):
        raise NotFound("Subject not found")


@register
class PreviewPaperImport(Capability[PaperImportPreviewInput, PaperImportPreviewResponse]):
    name = "paper_import.preview"
    description = "预检整卷导入:哪些题目可入库、哪些结构会降级、是否存在阻断问题。不写库。"
    input_model = PaperImportPreviewInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: PaperImportPreviewInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: PaperImportPreviewInput, target: Any
    ) -> PaperImportPreviewResponse:
        # 延迟导入:服务层依赖 composition_service,后者又依赖本包的 errors,顶层导入会成环。
        from app.services import paper_import_service

        preview = await paper_import_service.preview_paper_import(
            questions=inp.questions,
            outline=inp.outline,
            scope_type=inp.scope_type,
        )
        return PaperImportPreviewResponse(
            importable_count=preview.importable_count,
            skipped=[vars(s) for s in preview.skipped],
            degraded=[vars(d) for d in preview.degraded],
            blocking_reason=preview.blocking_reason,
        )


@register
class CommitPaperImport(Capability[PaperImportCommitInput, PaperImportCommitResponse]):
    name = "paper_import.commit"
    description = "提交整卷导入:在同一事务内写入题目,并按需创建可继续编辑的稿件。"
    input_model = PaperImportCommitInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_QUESTION
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: PaperImportCommitInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: PaperImportCommitInput, target: Any
    ) -> PaperImportCommitResponse:
        from app.services import paper_import_service
        from app.services.paper_import_service import PaperImportError

        try:
            result = await paper_import_service.commit_paper_import(
                ctx.db,
                actor=ctx.actor,
                subject_id=inp.subject_id,
                scope_type=inp.scope_type,
                owner_id=inp.owner_id,
                questions=inp.questions,
                outline=inp.outline,
                save_as_composition=inp.save_as_composition,
                title=inp.title,
                folder_id=inp.folder_id,
                renumber=inp.renumber,
                proceed_with_partial=inp.proceed_with_partial,
                default_status=inp.status,
                filename=inp.filename,
                file_path=inp.file_path,
                content_sha256=inp.content_sha256,
                idempotency_key=inp.idempotency_key,
            )
        except PaperImportError as exc:
            await ctx.db.rollback()
            raise Unprocessable(str(exc)) from exc

        await ctx.db.commit()
        return PaperImportCommitResponse(
            import_task_id=result.import_task_id,
            created_count=len(result.created_questions),
            created_question_ids=[q.id for q in result.created_questions],
            skipped=[vars(s) for s in result.skipped],
            degraded=[vars(d) for d in result.degraded],
            composition_id=result.composition_id,
            composition_title=result.composition_title,
            temp_id_map=result.temp_id_map,
            reused_existing=result.reused_existing,
        )
