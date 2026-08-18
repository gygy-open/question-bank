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
    TemplateItem,
    CreateFromTemplate,
    SaveAsTemplate,
)
from app.services.composition_renderer import composition_renderer, ContentPosition
from app.services.composition_templates import SYSTEM_TEMPLATES
from app.crud.crud_folder import folder as crud_folder
from app.models.composition import FolderScope

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_read(comp: models.Composition) -> CompositionRead:
    return CompositionRead(
        id=comp.id,
        title=comp.title,
        description=comp.description,
        status=comp.status,
        is_template=comp.is_template,
        difficulty=comp.difficulty,
        meta_data=comp.meta_data,
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
            question=QuestionBrief.model_validate(b.question) if b.question else None,
        )
        for b in comp.blocks
    ]
    return CompositionDetail(
        id=comp.id,
        title=comp.title,
        description=comp.description,
        status=comp.status,
        is_template=comp.is_template,
        difficulty=comp.difficulty,
        meta_data=comp.meta_data,
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
    subject_id: Optional[int] = None,
    scope: Optional[str] = None,
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
    # personal 空间只看自己的; team 空间全组共享, 不按 owner 过滤
    owner_filter = current_user.id if scope == "personal" else None
    comps = await crud.composition.list(
        db,
        owner_id=owner_filter,
        status=status,
        subject_id=subject_id,
        scope=scope,
        folder_id=folder_id,
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


@router.get("/templates/list", response_model=List[TemplateItem])
async def list_templates(
    *,
    db: deps.SessionDep,
    subject_id: Optional[int] = None,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """新建起点: 系统预置模板 + 当前学科下本人可见的自定义模板。"""
    if subject_id is None:
        subject_id = current_user.last_active_subject_id or current_user.subject_id
    items: List[TemplateItem] = [
        TemplateItem(
            source="system",
            key=t.key,
            label=t.label,
            icon=t.icon,
            description=t.description,
        )
        for t in SYSTEM_TEMPLATES.values()
    ]
    if subject_id is not None:
        customs = await crud.composition.list_templates(
            db, subject_id=subject_id, owner_id=current_user.id
        )
        items.extend(
            TemplateItem(
                source="custom",
                id=c.id,
                label=c.title,
                description=c.description,
                scope=c.scope,
            )
            for c in customs
        )
    return items


@router.post("/templates/new", response_model=CompositionRead)
async def create_from_template(
    *,
    db: deps.SessionDep,
    payload: CreateFromTemplate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """从模板新建 = 一次深拷贝, 不留来源关联。"""
    subject_id = payload.subject_id or current_user.last_active_subject_id or current_user.subject_id
    if payload.folder_id:
        folder_id = payload.folder_id
    else:
        scope = payload.scope.value if hasattr(payload.scope, "value") else payload.scope
        root = await crud_folder.ensure_root(
            db, owner_id=current_user.id, subject_id=subject_id, scope=scope
        )
        folder_id = root.id

    if payload.source == "custom":
        if not payload.template_id:
            raise HTTPException(status_code=422, detail="template_id required")
        tpl = await crud.composition.get_detail(
            db, comp_id=payload.template_id, owner_id=current_user.id
        )
        if not tpl or not tpl.is_template:
            raise HTTPException(status_code=404, detail="Template not found")
        new_comp = await crud.composition.duplicate(
            db,
            composition=tpl,
            title=payload.title or tpl.title,
            folder_id=folder_id,
            owner_id=current_user.id,
            is_template=False,
        )
        return _to_read(new_comp)

    template = SYSTEM_TEMPLATES.get(payload.key or "")
    if not template:
        raise HTTPException(status_code=404, detail="System template not found")
    new_comp = await crud.composition.create_from_system_template(
        db,
        template=template,
        title=payload.title or template.label,
        folder_id=folder_id,
        owner_id=current_user.id,
    )
    return _to_read(new_comp)


@router.post("/{comp_id}/save-as-template", response_model=CompositionRead)
async def save_as_template(
    *,
    db: deps.SessionDep,
    comp_id: int,
    payload: SaveAsTemplate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """把现有文档另存为自定义模板 (深拷贝, 存入按学科+空间隔离的模板库)。"""
    comp = await crud.composition.get_detail(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")
    subject_id = comp.subject_id or current_user.last_active_subject_id or current_user.subject_id
    scope = payload.scope.value if hasattr(payload.scope, "value") else payload.scope
    root = await crud_folder.ensure_root(
        db, owner_id=current_user.id, subject_id=subject_id, scope=scope
    )
    new_tpl = await crud.composition.duplicate(
        db,
        composition=comp,
        title=payload.title or comp.title,
        folder_id=root.id,
        owner_id=current_user.id,
        is_template=True,
    )
    return _to_read(new_tpl)


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


@router.post("/{comp_id}/download")
async def download_composition(
    *,
    db: deps.SessionDep,
    comp_id: int,
    options: CompositionExportOptions,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """Generate and download a composition preserving block order (WYSIWYG)."""
    comp = await crud.composition.get_owned(db, comp_id=comp_id, owner_id=current_user.id)
    if not comp:
        raise HTTPException(status_code=404, detail="Composition not found")

    blocks = await crud.composition.get_render_blocks(db, comp_id=comp_id)
    if not blocks:
        raise HTTPException(status_code=404, detail="Composition has no content")

    # 所见即所得: 答案显隐与落位由文档级设置决定, 不再每次导出选择
    meta = comp.meta_data or {}
    if meta.get("show_answers") is False:
        content_position = ContentPosition.HIDDEN
    else:
        try:
            content_position = ContentPosition(meta.get("answer_position", "after_question"))
        except ValueError:
            content_position = ContentPosition.AFTER_QUESTION

    title = options.title or comp.title
    try:
        file_path = composition_renderer.generate_file(
            title,
            blocks,
            options.format,
            content_position=content_position,
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
