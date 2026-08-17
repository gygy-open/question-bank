import os
import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from app.api import deps
from app import crud, models
from app.schemas.composition import (
    CompositionCreate,
    CompositionUpdate,
    BlocksReplace,
    CompositionExportOptions,
    CompositionRead,
    CompositionDetail,
    BlockRead,
    QuestionBrief,
)
from app.services.composition_renderer import composition_renderer

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_read(comp: models.Composition) -> CompositionRead:
    return CompositionRead(
        id=comp.id,
        comp_type=comp.comp_type,
        kind=comp.kind,
        title=comp.title,
        description=comp.description,
        status=comp.status,
        difficulty=comp.difficulty,
        folder_id=comp.folder_id,
        subject_id=comp.subject_id,
        scope=comp.scope,
        owner_id=comp.owner_id,
        created_at=comp.created_at,
        updated_at=comp.updated_at,
        block_count=len(comp.blocks),
    )


def _to_detail(comp: models.Composition) -> CompositionDetail:
    blocks = [
        BlockRead(
            id=b.id,
            block_type=b.block_type,
            sequence=b.sequence,
            content=b.content,
            ref_question_id=b.ref_question_id,
            ref_composition_id=b.ref_composition_id,
            question=QuestionBrief.model_validate(b.question) if b.question else None,
        )
        for b in comp.blocks
    ]
    return CompositionDetail(
        id=comp.id,
        comp_type=comp.comp_type,
        kind=comp.kind,
        title=comp.title,
        description=comp.description,
        status=comp.status,
        difficulty=comp.difficulty,
        folder_id=comp.folder_id,
        subject_id=comp.subject_id,
        scope=comp.scope,
        owner_id=comp.owner_id,
        created_at=comp.created_at,
        updated_at=comp.updated_at,
        block_count=len(blocks),
        blocks=blocks,
    )


@router.get("", response_model=List[CompositionRead])
async def list_compositions(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
    kind: Optional[str] = None,
    scope: Optional[str] = None,
    subject_id: Optional[int] = None,
    comp_type: Optional[str] = None,
    folder_id: Optional[int] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    difficulty: Optional[int] = None,
    sort: str = "updated_desc",
    skip: int = 0,
    limit: int = 100,
) -> Any:
    if subject_id is None:
        subject_id = current_user.last_active_subject_id or current_user.subject_id
    comps = await crud.composition.get_multi(
        db,
        current_user_id=current_user.id,
        kind=kind,
        scope=scope,
        subject_id=subject_id,
        comp_type=comp_type,
        folder_id=folder_id,
        status=status,
        keyword=keyword,
        difficulty=difficulty,
        sort=sort,
        skip=skip,
        limit=limit,
    )
    return [_to_read(c) for c in comps]


@router.post("", response_model=CompositionRead)
async def create_composition(
    *,
    db: deps.SessionDep,
    comp_in: CompositionCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    subject_id = comp_in.subject_id or current_user.last_active_subject_id or current_user.subject_id
    comp = await crud.composition.create_for_owner(
        db, obj_in=comp_in, owner_id=current_user.id, subject_id=subject_id
    )
    return _to_read(comp)


@router.get("/{comp_id}", response_model=CompositionDetail)
async def get_composition(
    *,
    db: deps.SessionDep,
    comp_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    comp = await crud.composition.get_detail(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")
    return _to_detail(comp)


@router.patch("/{comp_id}", response_model=CompositionRead)
async def update_composition(
    *,
    db: deps.SessionDep,
    comp_id: int,
    comp_in: CompositionUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    comp = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")
    comp = await crud.composition.update_composition(db, db_obj=comp, obj_in=comp_in)
    return _to_read(comp)


@router.delete("/{comp_id}")
async def delete_composition(
    *,
    db: deps.SessionDep,
    comp_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    comp = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")
    await db.delete(comp)
    await db.commit()
    return {"ok": True}


@router.post("/{comp_id}/duplicate", response_model=CompositionRead)
async def duplicate_composition(
    *,
    db: deps.SessionDep,
    comp_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    comp = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")
    new_comp = await crud.composition.duplicate(db, composition=comp)
    return _to_read(new_comp)


@router.put("/{comp_id}/blocks", response_model=CompositionDetail)
async def replace_blocks(
    *,
    db: deps.SessionDep,
    comp_id: int,
    payload: BlocksReplace,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    comp = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")
    await crud.composition.replace_blocks(db, composition=comp, blocks=payload.blocks)
    comp = await crud.composition.get_detail(db, comp_id=comp_id, owner_id=current_user.id)
    return _to_detail(comp)


@router.post("/{comp_id}/blocks/questions", response_model=CompositionDetail)
async def add_question_blocks(
    *,
    db: deps.SessionDep,
    comp_id: int,
    payload: dict,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """将若干题目作为题块追加到队尾 (试题篮加入题目)。"""
    question_ids = payload.get("question_ids") or []
    comp = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")
    await crud.composition.append_question_blocks(db, composition=comp, question_ids=question_ids)
    comp = await crud.composition.get_detail(db, comp_id=comp_id, owner_id=current_user.id)
    return _to_detail(comp)


@router.post("/{comp_id}/blocks/import-group/{group_id}", response_model=CompositionDetail)
async def import_group(
    *,
    db: deps.SessionDep,
    comp_id: int,
    group_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """引用式插入: 追加一个指向题组的 component_ref 块 (跟随更新)。"""
    target = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not target:
        raise HTTPException(status_code=404, detail="Composition not found")
    group = await crud.composition.get_owned(db, comp_id=group_id, owner_id=current_user.id)
    if not group:
        raise HTTPException(status_code=404, detail="Question group not found")
    await crud.composition.append_component_ref(db, composition=target, group_id=group_id)
    target = await crud.composition.get_detail(db, comp_id=comp_id, owner_id=current_user.id)
    return _to_detail(target)


@router.post("/{comp_id}/blocks/{block_id}/detach", response_model=CompositionDetail)
async def detach_component(
    *,
    db: deps.SessionDep,
    comp_id: int,
    block_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """拆开: 把某个 component_ref 块替换为被引题组块的深拷贝 (剥离引用)。"""
    comp = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")
    await crud.composition.detach_component_ref(db, composition=comp, block_id=block_id)
    comp = await crud.composition.get_detail(db, comp_id=comp_id, owner_id=current_user.id)
    return _to_detail(comp)


@router.post("/{comp_id}/download")
async def download_composition(
    *,
    db: deps.SessionDep,
    comp_id: int,
    options: CompositionExportOptions,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """Generate and download a composition preserving block order (component_ref expanded)."""
    comp = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")

    blocks = await crud.composition.get_render_blocks(db, comp_id=comp_id)
    if not blocks:
        raise HTTPException(status_code=404, detail="Composition has no content")

    title = options.title or comp.title
    try:
        file_path = composition_renderer.generate_file(
            title,
            blocks,
            options.format,
            content_position=options.content_position,
            include_answer=options.include_answer,
            include_analysis=options.include_analysis,
            include_explanation=options.include_explanation,
            include_summary=options.include_summary,
            include_source=options.include_source,
        )

        extension = options.format.value
        if extension == "latex":
            extension = "zip"
        filename = f"{title}.{extension}"

        def cleanup():
            if os.path.exists(file_path):
                os.remove(file_path)

        return FileResponse(
            path=file_path,
            filename=filename,
            background=BackgroundTask(cleanup),
        )
    except Exception as e:
        logger.error(f"Error generating composition: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
