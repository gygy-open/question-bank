"""整卷导入 API —— 预检与提交。

与组稿同构:Subject 强上下文 + scope=shared|personal;personal 的 owner_id 由服务端
强制为当前用户,客户端无从伪造。
"""
from typing import Any, Optional, Tuple

from fastapi import APIRouter, Depends

from app import capabilities, models
from app.api import deps
from app.capabilities import paper_imports as paper_import_caps
from app.models.composition import ScopeType
from app.schemas.paper_import import (
    PaperImportCommitRequest,
    PaperImportCommitResponse,
    PaperImportPreviewRequest,
    PaperImportPreviewResponse,
)

router = APIRouter()


def _resolve_scope(
    scope: ScopeType, current_user: models.User
) -> Tuple[ScopeType, Optional[int]]:
    if scope == ScopeType.PERSONAL:
        return scope, current_user.id
    return scope, None


@router.post(
    "/{subject_id}/paper-imports/preview",
    response_model=PaperImportPreviewResponse,
)
async def preview_paper_import(
    subject_id: int,
    payload: PaperImportPreviewRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    scope_type, owner_id = _resolve_scope(ScopeType(payload.scope), current_user)
    return await capabilities.run(
        "paper_import.preview",
        deps.api_context(db, current_user, subject_id=subject_id),
        paper_import_caps.PaperImportPreviewInput(
            subject_id=subject_id,
            scope_type=scope_type,
            owner_id=owner_id,
            questions=[q.model_dump() for q in payload.questions],
            outline=[o.model_dump() for o in payload.outline],
        ),
    )


@router.post("/{subject_id}/paper-imports", response_model=PaperImportCommitResponse)
async def commit_paper_import(
    subject_id: int,
    payload: PaperImportCommitRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    scope_type, owner_id = _resolve_scope(ScopeType(payload.scope), current_user)
    return await capabilities.run(
        "paper_import.commit",
        deps.api_context(db, current_user, subject_id=subject_id),
        paper_import_caps.PaperImportCommitInput(
            subject_id=subject_id,
            scope_type=scope_type,
            owner_id=owner_id,
            questions=[q.model_dump() for q in payload.questions],
            outline=[o.model_dump() for o in payload.outline],
            save_as_composition=payload.save_as_composition,
            title=payload.title,
            folder_id=payload.folder_id,
            renumber=payload.renumber,
            proceed_with_partial=payload.proceed_with_partial,
            status=payload.status,
            filename=payload.filename,
            file_path=payload.file_path,
            content_sha256=payload.content_sha256,
            idempotency_key=payload.idempotency_key,
        ),
    )
