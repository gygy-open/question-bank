from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from app import crud, schemas, models
from app.api import deps
from app.models.tag import Tag
from app.models.question import question_tags

router = APIRouter()

@router.get("", response_model=List[schemas.TagCategory])
async def read_tag_categories(
    db: deps.SessionDep,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve tag categories.
    """
    tag_categories = await crud.tag_category.get_multi(db, skip=skip, limit=limit)
    return tag_categories

@router.post("", response_model=schemas.TagCategory)
async def create_tag_category(
    *,
    db: deps.SessionDep,
    tag_category_in: schemas.TagCategoryCreate,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new tag category.
    """
    tag_category = await crud.tag_category.create(db=db, obj_in=tag_category_in)
    return tag_category

@router.put("/{id}", response_model=schemas.TagCategory)
async def update_tag_category(
    *,
    db: deps.SessionDep,
    id: int,
    tag_category_in: schemas.TagCategoryUpdate,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a tag category.
    """
    tag_category = await crud.tag_category.get(db=db, id=id)
    if not tag_category:
        raise HTTPException(status_code=404, detail="Tag category not found")
    tag_category = await crud.tag_category.update(db=db, db_obj=tag_category, obj_in=tag_category_in)
    return tag_category

@router.delete("/{id}", response_model=schemas.TagCategory)
async def delete_tag_category(
    *,
    db: deps.SessionDep,
    id: int,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a tag category.
    """
    tag_category = await crud.tag_category.get(db=db, id=id)
    if not tag_category:
        raise HTTPException(status_code=404, detail="Tag category not found")
    
    # Find all tags in this category
    result = await db.execute(select(Tag).where(Tag.category == tag_category.slug))
    tags = result.scalars().all()
    
    for tag in tags:
        # Delete associations in question_tags
        await db.execute(delete(question_tags).where(question_tags.c.tag_id == tag.id))
        # Delete the tag
        await db.delete(tag)

    await db.delete(tag_category)
    await db.commit()
    return tag_category
