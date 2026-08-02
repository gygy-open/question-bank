import os
import logging
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from app.api import deps
from app import crud, models
from app.crud.crud_question import question as question_crud
from app.schemas.paper import (
    PaperGenerateRequest,
    PaperCreate,
    PaperUpdate,
    PaperItemsAdd,
    PaperReorder,
    PaperItemUpdate,
    PaperExportOptions,
    PaperRead,
    PaperDetail,
    PaperItemRead,
    QuestionBrief,
)
from app.services.paper_generator import paper_generator

logger = logging.getLogger(__name__)

router = APIRouter()


def _to_read(paper: models.Paper) -> PaperRead:
    return PaperRead(
        id=paper.id,
        title=paper.title,
        description=paper.description,
        status=paper.status,
        subject_id=paper.subject_id,
        owner_id=paper.owner_id,
        created_at=paper.created_at,
        updated_at=paper.updated_at,
        question_count=len(paper.items),
    )


def _to_detail(paper: models.Paper) -> PaperDetail:
    items = [
        PaperItemRead(
            id=item.id,
            question_id=item.question_id,
            sequence=item.sequence,
            section_title=item.section_title,
            score=item.score,
            question=QuestionBrief.model_validate(item.question) if item.question else None,
        )
        for item in paper.items
    ]
    return PaperDetail(
        id=paper.id,
        title=paper.title,
        description=paper.description,
        status=paper.status,
        subject_id=paper.subject_id,
        owner_id=paper.owner_id,
        created_at=paper.created_at,
        updated_at=paper.updated_at,
        question_count=len(items),
        items=items,
    )


@router.get("", response_model=List[PaperRead])
async def list_papers(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    sort: str = "updated_desc",
    skip: int = 0,
    limit: int = 100,
) -> Any:
    papers = await crud.paper.get_multi_by_owner(
        db,
        owner_id=current_user.id,
        status=status,
        keyword=keyword,
        sort=sort,
        skip=skip,
        limit=limit,
    )
    return [_to_read(p) for p in papers]


@router.post("", response_model=PaperRead)
async def create_paper(
    *,
    db: deps.SessionDep,
    paper_in: PaperCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.create_for_owner(db, obj_in=paper_in, owner_id=current_user.id)
    return _to_read(paper)


@router.get("/{paper_id}", response_model=PaperDetail)
async def get_paper(
    *,
    db: deps.SessionDep,
    paper_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.get_detail(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return _to_detail(paper)


@router.patch("/{paper_id}", response_model=PaperRead)
async def update_paper(
    *,
    db: deps.SessionDep,
    paper_id: int,
    paper_in: PaperUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.get_owned(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    paper = await crud.paper.update(db, db_obj=paper, obj_in=paper_in)
    await db.refresh(paper, ["items"])
    return _to_read(paper)


@router.delete("/{paper_id}")
async def delete_paper(
    *,
    db: deps.SessionDep,
    paper_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.get_owned(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    await db.delete(paper)
    await db.commit()
    return {"ok": True}


@router.post("/{paper_id}/duplicate", response_model=PaperRead)
async def duplicate_paper(
    *,
    db: deps.SessionDep,
    paper_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.get_owned(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    new_paper = await crud.paper.duplicate(db, paper=paper)
    await db.refresh(new_paper, ["items"])
    return _to_read(new_paper)


@router.post("/{paper_id}/items", response_model=PaperDetail)
async def add_items(
    *,
    db: deps.SessionDep,
    paper_id: int,
    items_in: PaperItemsAdd,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.get_owned(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    await crud.paper.add_items(db, paper=paper, question_ids=items_in.question_ids)
    paper = await crud.paper.get_detail(db, paper_id=paper_id, owner_id=current_user.id)
    return _to_detail(paper)


@router.delete("/{paper_id}/items/{item_id}", response_model=PaperDetail)
async def remove_item(
    *,
    db: deps.SessionDep,
    paper_id: int,
    item_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.get_owned(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    removed = await crud.paper.remove_item(db, paper_id=paper_id, item_id=item_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Item not found")
    paper = await crud.paper.get_detail(db, paper_id=paper_id, owner_id=current_user.id)
    return _to_detail(paper)


@router.patch("/{paper_id}/items/{item_id}", response_model=PaperDetail)
async def update_item(
    *,
    db: deps.SessionDep,
    paper_id: int,
    item_id: int,
    item_in: PaperItemUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.get_owned(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    fields_set = item_in.model_fields_set
    updated = await crud.paper.update_item(
        db,
        paper_id=paper_id,
        item_id=item_id,
        section_title=item_in.section_title,
        score=item_in.score,
        clear_section_title="section_title" in fields_set and item_in.section_title is None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Item not found")
    paper = await crud.paper.get_detail(db, paper_id=paper_id, owner_id=current_user.id)
    return _to_detail(paper)


@router.put("/{paper_id}/items/order", response_model=PaperDetail)
async def reorder_items(
    *,
    db: deps.SessionDep,
    paper_id: int,
    reorder_in: PaperReorder,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    paper = await crud.paper.get_owned(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    try:
        await crud.paper.reorder(db, paper=paper, ordered_item_ids=reorder_in.ordered_item_ids)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    paper = await crud.paper.get_detail(db, paper_id=paper_id, owner_id=current_user.id)
    return _to_detail(paper)


@router.post("/{paper_id}/download")
async def download_managed_paper(
    *,
    db: deps.SessionDep,
    paper_id: int,
    options: PaperExportOptions,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """Generate and download a managed paper preserving question order."""
    paper = await crud.paper.get_owned(db, paper_id=paper_id, owner_id=current_user.id)
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    items = await crud.paper.get_ordered_items(db, paper_id=paper_id)
    if not items:
        raise HTTPException(status_code=404, detail="No questions in paper")

    questions = [item.question for item in items]
    section_titles = [item.section_title for item in items]

    title = options.title or paper.title
    try:
        file_path = paper_generator.generate_file(
            title,
            questions,
            options.format,
            include_answer=options.include_answer,
            include_analysis=options.include_analysis,
            include_explanation=options.include_explanation,
            include_summary=options.include_summary,
            include_source=options.include_source,
            section_titles=section_titles,
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
        logger.error(f"Error generating paper: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/download")
async def download_paper(
    request: PaperGenerateRequest,
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """
    [Legacy] Generate and download a paper from an ad-hoc question id list.
    Order is not guaranteed; prefer POST /papers/{id}/download.
    """
    questions = await question_crud.get_multi_by_ids(db, ids=request.question_ids)
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found")

    try:
        file_path = paper_generator.generate_file(
            request.title,
            questions,
            request.format,
            include_answer=request.include_answer,
            include_analysis=request.include_analysis,
            include_explanation=request.include_explanation,
            include_summary=request.include_summary,
            include_source=request.include_source
        )

        extension = request.format.value
        if extension == "latex":
            extension = "zip"

        filename = f"{request.title}.{extension}"

        def cleanup():
            if os.path.exists(file_path):
                os.remove(file_path)

        return FileResponse(
            path=file_path,
            filename=filename,
            background=BackgroundTask(cleanup)
        )
    except Exception as e:
        logger.error(f"Error generating paper: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
