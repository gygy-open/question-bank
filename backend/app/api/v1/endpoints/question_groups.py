from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app import models
from app.api import deps
from app.core.permissions import Permission
from app.crud.crud_subject import subject as crud_subject
from app.schemas.question_group import (
    QuestionGroupCreate,
    QuestionGroupRead,
    QuestionGroupUpdate,
    StimulusCreate,
    StimulusRead,
    StimulusUpdate,
)
from app.services import question_group_service


router = APIRouter()


async def _require_subject(db: deps.SessionDep, subject_id: int) -> None:
    if await crud_subject.get(db, id=subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found")


@router.post(
    "/{subject_id}/stimuli", response_model=StimulusRead, status_code=status.HTTP_201_CREATED
)
async def create_stimulus(
    subject_id: int,
    payload: StimulusCreate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    if payload.content is None:
        raise HTTPException(status_code=422, detail="Stimulus content is required")
    return await question_group_service.create_stimulus(
        db,
        subject_id=subject_id,
        content=payload.content,
        status_value=payload.status.value,
        visibility=payload.visibility.value,
        actor=current_user,
        source=payload.source,
        metadata=payload.metadata,
    )


@router.get("/{subject_id}/stimuli/{stimulus_id}", response_model=StimulusRead)
async def read_stimulus(
    subject_id: int,
    stimulus_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    stimulus = await question_group_service.get_stimulus(db, stimulus_id, current_user)
    if stimulus.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Stimulus not found")
    return stimulus


@router.put("/{subject_id}/stimuli/{stimulus_id}", response_model=StimulusRead)
async def update_stimulus(
    subject_id: int,
    stimulus_id: int,
    payload: StimulusUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    stimulus = await question_group_service.get_stimulus(db, stimulus_id, current_user)
    if stimulus.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Stimulus not found")
    return await question_group_service.update_stimulus(
        db,
        stimulus=stimulus,
        expected_revision=payload.expected_revision,
        actor=current_user,
        content=payload.content,
        status_value=payload.status.value if payload.status is not None else None,
        visibility=payload.visibility.value if payload.visibility is not None else None,
        source=payload.source,
        metadata=payload.metadata,
    )


@router.post(
    "/{subject_id}/question-groups",
    response_model=QuestionGroupRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_question_group(
    subject_id: int,
    payload: QuestionGroupCreate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    return await question_group_service.create_group(
        db,
        subject_id=subject_id,
        stimulus_id=payload.stimulus_id,
        items=payload.items,
        status_value=payload.status.value,
        visibility=payload.visibility.value,
        actor=current_user,
        source=payload.source,
        metadata=payload.metadata,
    )


@router.get(
    "/{subject_id}/question-groups/{group_id}", response_model=QuestionGroupRead
)
async def read_question_group(
    subject_id: int,
    group_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    group = await question_group_service.get_group(db, group_id, current_user)
    if group.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Question group not found")
    return group


@router.put(
    "/{subject_id}/question-groups/{group_id}", response_model=QuestionGroupRead
)
async def update_question_group(
    subject_id: int,
    group_id: int,
    payload: QuestionGroupUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    group = await question_group_service.get_group(db, group_id, current_user)
    if group.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Question group not found")
    return await question_group_service.update_group(
        db,
        group=group,
        expected_revision=payload.expected_revision,
        actor=current_user,
        stimulus_id=payload.stimulus_id,
        items=payload.items,
        status_value=payload.status.value if payload.status is not None else None,
        visibility=payload.visibility.value if payload.visibility is not None else None,
        source=payload.source,
        metadata=payload.metadata,
    )


@router.delete(
    "/{subject_id}/question-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_question_group(
    subject_id: int,
    group_id: int,
    db: deps.SessionDep,
    expected_revision: int = Query(..., ge=1),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Response:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    group = await question_group_service.get_group(db, group_id, current_user)
    if group.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Question group not found")
    await question_group_service.delete_group(
        db, group=group, expected_revision=expected_revision, actor=current_user
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)