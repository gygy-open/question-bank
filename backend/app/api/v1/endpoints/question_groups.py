import math
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app import models
from app.api import deps
from app.core.permissions import Permission
from app.crud.crud_question_group import question_group as crud_question_group
from app.crud.crud_question_group import stimulus as crud_stimulus
from app.crud.crud_subject import subject as crud_subject
from app.schemas.question_group import (
    QuestionGroupCreate,
    QuestionGroupPage,
    QuestionGroupRead,
    QuestionGroupUpdate,
    RestoreRequest,
    StimulusCreate,
    StimulusListItem,
    StimulusPage,
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


@router.get("/{subject_id}/stimuli", response_model=StimulusPage)
async def read_stimuli(
    subject_id: int,
    db: deps.SessionDep,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = None,
    status_value: Optional[str] = Query(None, alias="status"),
    visibility: Optional[str] = None,
    only_deleted: bool = False,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    rows, total = await crud_stimulus.get_page(
        db,
        subject_id=subject_id,
        viewer_id=current_user.id,
        is_superuser=current_user.is_superuser,
        skip=(page - 1) * size,
        limit=size,
        keyword=keyword,
        status=status_value,
        visibility=visibility,
        only_deleted=only_deleted,
    )
    items = [
        StimulusListItem.model_validate(stimulus).model_copy(
            update={"question_group_count": group_count}
        )
        for stimulus, group_count in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size),
    }


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


@router.delete(
    "/{subject_id}/stimuli/{stimulus_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_stimulus(
    subject_id: int,
    stimulus_id: int,
    db: deps.SessionDep,
    expected_revision: int = Query(..., ge=1),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Response:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    stimulus = await question_group_service.get_stimulus(db, stimulus_id, current_user)
    if stimulus.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Stimulus not found")
    await question_group_service.delete_stimulus(
        db, stimulus=stimulus, expected_revision=expected_revision, actor=current_user
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{subject_id}/stimuli/{stimulus_id}/restore", response_model=StimulusRead)
async def restore_stimulus(
    subject_id: int,
    stimulus_id: int,
    payload: RestoreRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    stimulus = await question_group_service.get_deleted_stimulus(
        db, stimulus_id, current_user
    )
    if stimulus.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Stimulus not found")
    return await question_group_service.restore_stimulus(
        db, stimulus=stimulus, expected_revision=payload.expected_revision, actor=current_user
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


@router.get("/{subject_id}/question-groups", response_model=QuestionGroupPage)
async def read_question_groups(
    subject_id: int,
    db: deps.SessionDep,
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    keyword: Optional[str] = None,
    status_value: Optional[str] = Query(None, alias="status"),
    visibility: Optional[str] = None,
    stimulus_id: Optional[int] = None,
    question_id: Optional[int] = None,
    only_deleted: bool = False,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    items, total = await crud_question_group.get_page(
        db,
        subject_id=subject_id,
        viewer_id=current_user.id,
        is_superuser=current_user.is_superuser,
        skip=(page - 1) * size,
        limit=size,
        keyword=keyword,
        status=status_value,
        visibility=visibility,
        stimulus_id=stimulus_id,
        question_id=question_id,
        only_deleted=only_deleted,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size),
    }


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


@router.post(
    "/{subject_id}/question-groups/{group_id}/restore",
    response_model=QuestionGroupRead,
)
async def restore_question_group(
    subject_id: int,
    group_id: int,
    payload: RestoreRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    group = await question_group_service.get_deleted_group(db, group_id, current_user)
    if group.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Question group not found")
    return await question_group_service.restore_group(
        db, group=group, expected_revision=payload.expected_revision, actor=current_user
    )