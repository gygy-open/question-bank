from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from app import crud, schemas, models
from app.api import deps

router = APIRouter()

@router.get("", response_model=List[schemas.Subject])
async def read_subjects(
    db: deps.SessionDep,
    skip: int = 0,
    limit: int = 100,
) -> Any:
    subjects = await crud.subject.get_multi(db, skip=skip, limit=limit)
    return subjects

@router.post("", response_model=schemas.Subject)
async def create_subject(
    *,
    db: deps.SessionDep,
    subject_in: schemas.SubjectCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    subject = await crud.subject.create(db=db, obj_in=subject_in, user_id=current_user.id)
    return subject

@router.put("/{id}", response_model=schemas.Subject)
async def update_subject(
    *,
    db: deps.SessionDep,
    id: int,
    subject_in: schemas.SubjectUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    subject = await crud.subject.get(db=db, id=id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    subject = await crud.subject.update(db=db, db_obj=subject, obj_in=subject_in, user_id=current_user.id)
    return subject

@router.get("/{id}", response_model=schemas.Subject)
async def read_subject(
    *,
    db: deps.SessionDep,
    id: int,
) -> Any:
    subject = await crud.subject.get(db=db, id=id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject

@router.delete("/{id}", response_model=schemas.Subject)
async def delete_subject(
    *,
    db: deps.SessionDep,
    id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    subject = await crud.subject.get(db=db, id=id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    subject = await crud.subject.remove(db=db, id=id, user_id=current_user.id)
    return subject
