from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from app import crud, schemas, models
from app.api import deps
from app.crud import crud_user
from app.core.permissions import Capability

router = APIRouter()

@router.get("", response_model=List[schemas.Subject])
async def read_subjects(
    db: deps.SessionDep,
    skip: int = 0,
    limit: int = 100,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    subjects = await crud.subject.get_multi(db, skip=skip, limit=limit)
    accessible = deps.permissions.accessible_subject_ids(current_user)
    if accessible is None:
        return subjects
    return [s for s in subjects if s.id in accessible]

@router.post("", response_model=schemas.Subject)
async def create_subject(
    *,
    db: deps.SessionDep,
    subject_in: schemas.SubjectCreate,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    subject = await crud.subject.create(db=db, obj_in=subject_in, user_id=current_user.id)
    return subject

@router.put("/{id}", response_model=schemas.Subject)
async def update_subject(
    *,
    db: deps.SessionDep,
    id: int,
    subject_in: schemas.SubjectUpdate,
    current_user: models.User = Depends(deps.get_current_active_superuser),
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
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    subject = await crud.subject.get(db=db, id=id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    subject = await crud.subject.remove(db=db, id=id, user_id=current_user.id)
    return subject


def _member_out(m: models.SubjectMember) -> schemas.SubjectMemberOut:
    return schemas.SubjectMemberOut(
        id=m.id,
        user_id=m.user_id,
        subject_id=m.subject_id,
        role=m.role,
        username=m.user.username if m.user else None,
        full_name=m.user.full_name if m.user else None,
    )


@router.get("/{subject_id}/members", response_model=List[schemas.SubjectMemberOut])
async def list_subject_members(
    *,
    db: deps.SessionDep,
    subject_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    deps.require(current_user, Capability.MANAGE_MEMBERS, subject_id=subject_id)
    members = await crud.subject_member.list_by_subject(db, subject_id=subject_id)
    return [_member_out(m) for m in members]


@router.put("/{subject_id}/members/{user_id}", response_model=schemas.SubjectMemberOut)
async def set_subject_member(
    *,
    db: deps.SessionDep,
    subject_id: int,
    user_id: int,
    body: schemas.SubjectMemberSetRole,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    deps.require(current_user, Capability.MANAGE_MEMBERS, subject_id=subject_id)
    subject = await crud.subject.get(db=db, id=subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    target = await crud_user.user.get(db, id=user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    await crud.subject_member.set_role(
        db, user_id=user_id, subject_id=subject_id, role=body.role
    )
    member = await crud.subject_member.get(db, user_id=user_id, subject_id=subject_id)
    return _member_out(member)


@router.delete("/{subject_id}/members/{user_id}")
async def remove_subject_member(
    *,
    db: deps.SessionDep,
    subject_id: int,
    user_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    deps.require(current_user, Capability.MANAGE_MEMBERS, subject_id=subject_id)
    ok = await crud.subject_member.remove_member(db, user_id=user_id, subject_id=subject_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Member not found")
    return {"ok": True}
