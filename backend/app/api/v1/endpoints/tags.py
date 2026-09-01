import math
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from app import crud, schemas, models
from app.api import deps
from app.services import tag_import_service

router = APIRouter()

MAX_IMPORT_SIZE = 5 * 1024 * 1024  # 5 MB

@router.get("", response_model=schemas.TagPage)
async def read_tags(
    db: deps.SessionDep,
    subject_id: int,
    page: int = 1,
    size: int = 20,
    category_id: Optional[int] = None,
) -> Any:
    """Set size to -1 to retrieve all tags for the subject (used by tag-picker UIs)."""
    limit = None if size == -1 else size
    skip = 0 if limit is None else (page - 1) * size
    tags = await crud.tag.get_multi_by_subject(
        db, subject_id=subject_id, skip=skip, limit=limit, category_id=category_id
    )
    total = await crud.tag.count_by_subject(db, subject_id=subject_id, category_id=category_id)
    return {
        "items": tags,
        "total": total,
        "page": 1 if limit is None else page,
        "size": size,
        "pages": 1 if limit is None else (math.ceil(total / size) if size > 0 else 0),
    }

@router.post("", response_model=schemas.Tag)
async def create_tag(
    *,
    db: deps.SessionDep,
    tag_in: schemas.TagCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    # Check if tag exists within the same subject
    existing = await crud.tag.get_by_name_in_subject(
        db, name=tag_in.name, subject_id=tag_in.subject_id
    )
    if existing:
        raise HTTPException(status_code=400, detail="Tag with this name already exists")

    tag = await crud.tag.create(db=db, obj_in=tag_in, user_id=current_user.id)
    return tag

@router.get("/import-template")
async def download_import_template(
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """Download the .xlsx tag import template."""
    content = tag_import_service.generate_template()
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="tags_template.xlsx"'
        },
    )

@router.post("/import", response_model=schemas.TagImportResult)
async def import_tags(
    *,
    db: deps.SessionDep,
    subject_id: int,
    file: UploadFile = File(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """Batch import tags from an .xlsx file for a subject."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式的文件")

    content = await file.read()
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，请确保文件小于 5MB")

    return await tag_import_service.import_excel(
        db, subject_id=subject_id, file_bytes=content, user_id=current_user.id
    )

@router.put("/{id}", response_model=schemas.Tag)
async def update_tag(
    *,
    db: deps.SessionDep,
    id: int,
    tag_in: schemas.TagUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    tag = await crud.tag.get(db=db, id=id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    tag = await crud.tag.update(db=db, db_obj=tag, obj_in=tag_in, user_id=current_user.id)
    return tag

@router.get("/{id}", response_model=schemas.Tag)
async def read_tag(
    *,
    db: deps.SessionDep,
    id: int,
) -> Any:
    tag = await crud.tag.get(db=db, id=id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    return tag

@router.delete("/{id}", response_model=schemas.Tag)
async def delete_tag(
    *,
    db: deps.SessionDep,
    id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    tag = await crud.tag.get(db=db, id=id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    tag = await crud.tag.remove(db=db, id=id, user_id=current_user.id)
    return tag
