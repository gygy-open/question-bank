import math
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app import models
from app.api import deps
from app.core.permissions import Permission
from app.crud.crud_stimulus import stimulus as crud_stimulus
from app.crud.crud_subject import subject as crud_subject
from app.schemas.stimulus import (
    RestoreRequest,
    StimulusBundleCreate,
    StimulusBundleUpdate,
    StimulusCreate,
    StimulusDetail,
    StimulusListItem,
    StimulusPage,
    StimulusQuestionsUpdate,
    StimulusRead,
    StimulusUpdate,
)
from app.services import stimulus_service


router = APIRouter()


async def _require_subject(db: deps.SessionDep, subject_id: int) -> None:
    if await crud_subject.get(db, id=subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found")


async def _scoped_stimulus(
    db: deps.SessionDep, subject_id: int, stimulus_id: int, actor: models.User
) -> models.Stimulus:
    stimulus = await stimulus_service.get_stimulus(db, stimulus_id, actor)
    if stimulus.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Stimulus not found")
    return stimulus


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
    return await stimulus_service.create_stimulus(
        db,
        subject_id=subject_id,
        content=payload.content,
        status_value=payload.status.value,
        visibility=payload.visibility.value,
        actor=current_user,
        source=payload.source,
        metadata=payload.metadata,
    )


@router.post(
    "/{subject_id}/stimuli/bundle",
    response_model=StimulusDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_stimulus_bundle(
    subject_id: int,
    payload: StimulusBundleCreate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    return await stimulus_service.save_bundle(
        db, subject_id=subject_id, payload=payload, actor=current_user
    )


@router.put("/{subject_id}/stimuli/{stimulus_id}/bundle", response_model=StimulusDetail)
async def update_stimulus_bundle(
    subject_id: int,
    stimulus_id: int,
    payload: StimulusBundleUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    stimulus = await _scoped_stimulus(db, subject_id, stimulus_id, current_user)
    return await stimulus_service.save_bundle(
        db, subject_id=subject_id, payload=payload, actor=current_user, stimulus=stimulus
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
            update={"question_count": question_count}
        )
        for stimulus, question_count in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size),
    }


@router.get("/{subject_id}/stimuli/{stimulus_id}", response_model=StimulusDetail)
async def read_stimulus(
    subject_id: int,
    stimulus_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    stimulus = await _scoped_stimulus(db, subject_id, stimulus_id, current_user)
    return await stimulus_service.to_detail(db, stimulus, current_user)


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
    stimulus = await _scoped_stimulus(db, subject_id, stimulus_id, current_user)
    return await stimulus_service.update_stimulus(
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


@router.put(
    "/{subject_id}/stimuli/{stimulus_id}/questions", response_model=StimulusDetail
)
async def set_stimulus_questions(
    subject_id: int,
    stimulus_id: int,
    payload: StimulusQuestionsUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    stimulus = await _scoped_stimulus(db, subject_id, stimulus_id, current_user)
    return await stimulus_service.set_stimulus_questions(
        db,
        stimulus=stimulus,
        expected_revision=payload.expected_revision,
        question_ids=payload.question_ids,
        actor=current_user,
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
    stimulus = await _scoped_stimulus(db, subject_id, stimulus_id, current_user)
    await stimulus_service.delete_stimulus(
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
    stimulus = await stimulus_service.get_deleted_stimulus(db, stimulus_id, current_user)
    if stimulus.subject_id != subject_id:
        raise HTTPException(status_code=404, detail="Stimulus not found")
    return await stimulus_service.restore_stimulus(
        db, stimulus=stimulus, expected_revision=payload.expected_revision, actor=current_user
    )
