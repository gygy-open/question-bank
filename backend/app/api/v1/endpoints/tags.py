from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from app import crud, schemas, models
from app.api import deps

router = APIRouter()

@router.get("", response_model=List[schemas.Tag])
async def read_tags(
    db: deps.SessionDep,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    tags = await crud.tag.get_multi(db, skip=skip, limit=limit)
    return tags

@router.post("", response_model=schemas.Tag)
async def create_tag(
    *,
    db: deps.SessionDep,
    tag_in: schemas.TagCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    # Check if tag exists
    stmt = select(models.Tag).where(models.Tag.name == tag_in.name)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tag with this name already exists")

    tag = await crud.tag.create(db=db, obj_in=tag_in, user_id=current_user.id)
    return tag

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
