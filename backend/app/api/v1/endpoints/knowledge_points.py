from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from app import crud, schemas, models
from app.api import deps

router = APIRouter()

@router.get("", response_model=List[schemas.KnowledgePoint])
async def read_knowledge_points(
    db: deps.SessionDep,
    skip: int = 0,
    limit: int = 100,
    subject_id: Optional[int] = None,
) -> Any:
    """
    Retrieve knowledge points.
    Set limit to -1 to retrieve all knowledge points.
    """
    if limit == -1:
        limit = None
        
    if subject_id:
        knowledge_points = await crud.knowledge_point.get_by_subject(db, subject_id=subject_id, skip=skip, limit=limit)
    else:
        knowledge_points = await crud.knowledge_point.get_multi(db, skip=skip, limit=limit)
    return knowledge_points

@router.post("", response_model=schemas.KnowledgePoint)
async def create_knowledge_point(
    *,
    db: deps.SessionDep,
    knowledge_point_in: schemas.KnowledgePointCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    try:
        knowledge_point = await crud.knowledge_point.create(db=db, obj_in=knowledge_point_in, user_id=current_user.id)
        return knowledge_point
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Knowledge point with this slug already exists in this subject")

@router.put("/{id}", response_model=schemas.KnowledgePoint)
async def update_knowledge_point(
    *,
    db: deps.SessionDep,
    id: int,
    knowledge_point_in: schemas.KnowledgePointUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    knowledge_point = await crud.knowledge_point.get(db=db, id=id)
    if not knowledge_point:
        raise HTTPException(status_code=404, detail="Knowledge point not found")
    knowledge_point = await crud.knowledge_point.update(db=db, db_obj=knowledge_point, obj_in=knowledge_point_in, user_id=current_user.id)
    return knowledge_point

@router.get("/{id}", response_model=schemas.KnowledgePoint)
async def read_knowledge_point(
    *,
    db: deps.SessionDep,
    id: int,
) -> Any:
    """
    Get knowledge point by ID.
    """
    knowledge_point = await crud.knowledge_point.get(db=db, id=id)
    if not knowledge_point:
        raise HTTPException(status_code=404, detail="Knowledge point not found")
    return knowledge_point

@router.delete("/{id}", response_model=schemas.KnowledgePoint)
async def delete_knowledge_point(
    *,
    db: deps.SessionDep,
    id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Delete a knowledge point.
    """
    knowledge_point = await crud.knowledge_point.get(db=db, id=id)
    if not knowledge_point:
        raise HTTPException(status_code=404, detail="Knowledge point not found")
    knowledge_point = await crud.knowledge_point.remove(db=db, id=id, user_id=current_user.id)
    return knowledge_point
