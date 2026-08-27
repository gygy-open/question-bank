"""Folder / Composition 元数据 CRUD API —— 第二阶段最小可用切片。

路由采用 Subject 强上下文:/subjects/{subject_id}/folders 与 /subjects/{subject_id}/compositions,
范围经 query 参数 scope=shared|personal 选择。所有取用/修改都通过 scoped 查询强制
subject/scope/owner,personal 强制 owner_id=current_user.id;不做 Block patch / 定稿。
"""
import os
from typing import Any, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app import crud, models
from app.api import deps
from app.crud import crud_composition
from app.models.composition import ScopeType
from app.schemas.composition import (
    CompositionCreateRequest,
    CompositionDetail,
    CompositionEventPage,
    CompositionExportRequest,
    CompositionMetaUpdateRequest,
    CompositionNodesReplaceRequest,
    CompositionNodesReplaceResponse,
    CompositionQuestionNodesSyncRequest,
    CompositionQuestionNodesSyncResponse,
    CompositionRead,
    CompositionVersionCreateRequest,
    CompositionVersionRead,
    CompositionVersionSummary,
    FolderCreateRequest,
    FolderRead,
    FolderUpdateRequest,
    QuestionRevisionStatus,
)
from app.schemas.paper import OutputFormat
from app.services import composition_service
from app.services.exporting.composition_assemble import CompositionAssembler, CompositionExportError
from app.services.exporting.composition_registry import composition_renderer_for

router = APIRouter()


def _resolve_scope(
    scope: ScopeType, current_user: models.User
) -> Tuple[ScopeType, Optional[int]]:
    """shared → owner_id=None(团队可见);personal → owner_id 强制为当前用户,客户端无从伪造。"""
    if scope == ScopeType.PERSONAL:
        return scope, current_user.id
    return scope, None


async def _ensure_subject(db: deps.SessionDep, subject_id: int) -> None:
    subject = await crud.subject.get(db, id=subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")


# --------------------------------------------------------------------------- #
# Folders
# --------------------------------------------------------------------------- #
@router.get("/{subject_id}/folders", response_model=List[FolderRead])
async def list_folders(
    subject_id: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    return await crud_composition.folder.list_scoped(
        db, subject_id=subject_id, scope_type=scope_type, owner_id=owner_id
    )


@router.post("/{subject_id}/folders", response_model=FolderRead, status_code=status.HTTP_201_CREATED)
async def create_folder(
    subject_id: int,
    payload: FolderCreateRequest,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    return await composition_service.create_folder(
        db,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        actor=current_user,
        name=payload.name,
        parent_id=payload.parent_id,
    )


@router.patch("/{subject_id}/folders/{folder_id}", response_model=FolderRead)
async def update_folder(
    subject_id: int,
    folder_id: int,
    payload: FolderUpdateRequest,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    folder = await crud_composition.folder.get_scoped(
        db,
        folder_id=folder_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return await composition_service.update_folder(
        db,
        folder=folder,
        actor=current_user,
        name=payload.name,
        parent_id=payload.parent_id,
        parent_id_provided="parent_id" in payload.model_fields_set,
    )


@router.delete("/{subject_id}/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_folder(
    subject_id: int,
    folder_id: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> None:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    folder = await crud_composition.folder.get_scoped(
        db,
        folder_id=folder_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    await composition_service.delete_folder(db, folder=folder, actor=current_user)


# --------------------------------------------------------------------------- #
# Compositions
# --------------------------------------------------------------------------- #
@router.get("/{subject_id}/compositions", response_model=List[CompositionRead])
async def list_compositions(
    subject_id: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    folder_id: Optional[int] = None,
    root_only: bool = False,
    include_deleted: bool = False,
    only_deleted: bool = False,
    keyword: Optional[str] = None,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    return await crud_composition.composition.list_scoped(
        db,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        folder_id=folder_id,
        root_only=root_only,
        include_deleted=include_deleted,
        only_deleted=only_deleted,
        keyword=keyword,
    )


@router.post(
    "/{subject_id}/compositions",
    response_model=CompositionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_composition(
    subject_id: int,
    payload: CompositionCreateRequest,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    return await composition_service.create_composition(
        db,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        actor=current_user,
        title=payload.title,
        description=payload.description,
        folder_id=payload.folder_id,
    )


@router.get("/{subject_id}/compositions/{composition_id}", response_model=CompositionDetail)
async def get_composition(
    subject_id: int,
    composition_id: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    include_deleted: bool = False,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        include_deleted=include_deleted,
        with_nodes=True,
    )
    if comp is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    return comp


@router.patch("/{subject_id}/compositions/{composition_id}", response_model=CompositionRead)
async def update_composition(
    subject_id: int,
    composition_id: int,
    payload: CompositionMetaUpdateRequest,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if comp is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    return await composition_service.update_composition(
        db,
        comp=comp,
        actor=current_user,
        expected_revision=payload.expected_revision,
        title=payload.title,
        description=payload.description,
        status_value=payload.status.value if payload.status is not None else None,
        folder_id=payload.folder_id,
        folder_id_provided="folder_id" in payload.model_fields_set,
        numbering_enabled=payload.numbering_enabled,
        scoring_enabled=payload.scoring_enabled,
        question_display=payload.question_display,
    )


@router.put(
    "/{subject_id}/compositions/{composition_id}/nodes",
    response_model=CompositionNodesReplaceResponse,
)
async def replace_composition_nodes(
    subject_id: int,
    composition_id: int,
    payload: CompositionNodesReplaceRequest,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if comp is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    revision, nodes = await composition_service.replace_nodes(
        db,
        comp=comp,
        actor=current_user,
        expected_revision=payload.expected_revision,
        batch_id=payload.batch_id,
        items=payload.nodes,
    )
    return CompositionNodesReplaceResponse(revision=revision, nodes=nodes)


@router.get(
    "/{subject_id}/compositions/{composition_id}/question-revisions",
    response_model=List[QuestionRevisionStatus],
)
async def get_question_revisions(
    subject_id: int,
    composition_id: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if comp is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    return await composition_service.question_revision_status(db, comp=comp)


@router.post(
    "/{subject_id}/compositions/{composition_id}/question-nodes/sync",
    response_model=CompositionQuestionNodesSyncResponse,
)
async def sync_question_nodes(
    subject_id: int,
    composition_id: int,
    payload: CompositionQuestionNodesSyncRequest,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if comp is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    revision, nodes = await composition_service.sync_question_nodes(
        db,
        comp=comp,
        actor=current_user,
        expected_revision=payload.expected_revision,
        node_ids=payload.node_ids,
    )
    return CompositionQuestionNodesSyncResponse(revision=revision, nodes=nodes)


@router.delete(
    "/{subject_id}/compositions/{composition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_composition(
    subject_id: int,
    composition_id: int,
    db: deps.SessionDep,
    expected_revision: int = Query(...),
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> None:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if comp is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    await composition_service.delete_composition(
        db, comp=comp, actor=current_user, expected_revision=expected_revision
    )


@router.post(
    "/{subject_id}/compositions/{composition_id}/restore",
    response_model=CompositionRead,
)
async def restore_composition(
    subject_id: int,
    composition_id: int,
    db: deps.SessionDep,
    expected_revision: int = Query(...),
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        include_deleted=True,
    )
    if comp is None or comp.deleted_at is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    return await composition_service.restore_composition(
        db, comp=comp, actor=current_user, expected_revision=expected_revision
    )


@router.post(
    "/{subject_id}/compositions/{composition_id}/duplicate",
    response_model=CompositionRead,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_composition(
    subject_id: int,
    composition_id: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
    )
    if comp is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    return await composition_service.duplicate_composition(db, source=comp, actor=current_user)


# --------------------------------------------------------------------------- #
# Composition Versions (定稿)
# --------------------------------------------------------------------------- #
async def _scoped_composition_for_versions(
    db: deps.SessionDep,
    *,
    subject_id: int,
    composition_id: int,
    scope: ScopeType,
    current_user: models.User,
):
    """版本读写共用:先做 subject/scope/owner 可见性校验(不可见 404)。

    软删除稿仍可见(允许查看历史版本);是否允许新定稿由 service 层进一步裁决。
    """
    await _ensure_subject(db, subject_id)
    scope_type, owner_id = _resolve_scope(scope, current_user)
    comp = await crud_composition.composition.get_scoped(
        db,
        composition_id=composition_id,
        subject_id=subject_id,
        scope_type=scope_type,
        owner_id=owner_id,
        include_deleted=True,
    )
    if comp is None:
        raise HTTPException(status_code=404, detail="Composition not found")
    return comp


@router.post(
    "/{subject_id}/compositions/{composition_id}/versions",
    response_model=CompositionVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_composition_version(
    subject_id: int,
    composition_id: int,
    payload: CompositionVersionCreateRequest,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    comp = await _scoped_composition_for_versions(
        db,
        subject_id=subject_id,
        composition_id=composition_id,
        scope=scope,
        current_user=current_user,
    )
    return await composition_service.finalize_version(
        db,
        comp=comp,
        actor=current_user,
        expected_revision=payload.expected_revision,
        label=payload.label,
    )


@router.get(
    "/{subject_id}/compositions/{composition_id}/versions",
    response_model=List[CompositionVersionSummary],
)
async def list_composition_versions(
    subject_id: int,
    composition_id: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _scoped_composition_for_versions(
        db,
        subject_id=subject_id,
        composition_id=composition_id,
        scope=scope,
        current_user=current_user,
    )
    return await crud_composition.composition.list_versions(
        db, composition_id=composition_id
    )


@router.get(
    "/{subject_id}/compositions/{composition_id}/versions/{version_no}",
    response_model=CompositionVersionRead,
)
async def get_composition_version(
    subject_id: int,
    composition_id: int,
    version_no: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _scoped_composition_for_versions(
        db,
        subject_id=subject_id,
        composition_id=composition_id,
        scope=scope,
        current_user=current_user,
    )
    version = await crud_composition.composition.get_version(
        db, composition_id=composition_id, version_no=version_no
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")
    return version


@router.post("/{subject_id}/compositions/{composition_id}/versions/{version_no}/export")
async def export_composition_version(
    subject_id: int,
    composition_id: int,
    version_no: int,
    payload: CompositionExportRequest,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _scoped_composition_for_versions(
        db,
        subject_id=subject_id,
        composition_id=composition_id,
        scope=scope,
        current_user=current_user,
    )
    version = await crud_composition.composition.get_version(
        db, composition_id=composition_id, version_no=version_no
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Version not found")

    try:
        export_doc = CompositionAssembler().assemble(version.snapshot)
    except CompositionExportError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "detail": exc.detail,
                "node_id": exc.node_id,
                "node_type": exc.node_type,
                "version_no": version_no,
            },
        ) from exc

    if payload.title:
        export_doc.title = payload.title

    file_path = composition_renderer_for(payload.format).render(export_doc)
    suffix = "-latex.zip" if payload.format == OutputFormat.LATEX else f".{payload.format.value}"
    filename = f"{export_doc.title}-v{version_no}{suffix}"

    def cleanup() -> None:
        if os.path.exists(file_path):
            os.remove(file_path)

    return FileResponse(path=file_path, filename=filename, background=BackgroundTask(cleanup))


# --------------------------------------------------------------------------- #
# Composition Events (时间线)
# --------------------------------------------------------------------------- #
@router.get(
    "/{subject_id}/compositions/{composition_id}/events",
    response_model=CompositionEventPage,
)
async def list_composition_events(
    subject_id: int,
    composition_id: int,
    db: deps.SessionDep,
    scope: ScopeType = Query(...),
    before_id: Optional[int] = None,
    limit: int = Query(30, ge=1, le=100),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """时间线只读查询;可见性与版本历史一致(含软删除稿),游标翻页按 id 倒序。"""
    await _scoped_composition_for_versions(
        db,
        subject_id=subject_id,
        composition_id=composition_id,
        scope=scope,
        current_user=current_user,
    )
    events, has_more = await crud_composition.composition.list_events(
        db, composition_id=composition_id, before_id=before_id, limit=limit
    )
    return CompositionEventPage(items=events, has_more=has_more)