from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException

from app import models
from app.api import deps
from app.crud.crud_subject import subject as crud_subject
from app.crud.crud_subject_prompt import subject_prompt as crud_subject_prompt
from app.schemas.subject_prompt import SubjectPromptOut, SubjectPromptUpdate
from app.services.prompts import SUBJECT_PROMPTS

router = APIRouter()


def _to_out(key: str, value: str | None) -> SubjectPromptOut:
    meta = SUBJECT_PROMPTS[key]
    return SubjectPromptOut(
        key=key,
        title=meta["title"],
        description=meta["description"],
        default=meta["default"],
        value=value,
        is_custom=value is not None,
    )


@router.get("/{subject_id}/prompts", response_model=List[SubjectPromptOut])
async def list_subject_prompts(
    subject_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """列出某科目的可覆盖提示词：含代码默认值、覆盖原文与是否已定制。"""
    subject = await crud_subject.get(db, id=subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    out = []
    for key in SUBJECT_PROMPTS:
        override = await crud_subject_prompt.get_value(db, subject_id, key)
        out.append(_to_out(key, override))
    return out


@router.put("/{subject_id}/prompts/{key}", response_model=SubjectPromptOut)
async def update_subject_prompt(
    subject_id: int,
    key: str,
    payload: SubjectPromptUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """保存某科目对某提示词的覆盖。"""
    if key not in SUBJECT_PROMPTS:
        raise HTTPException(status_code=404, detail="Unknown prompt key")
    subject = await crud_subject.get(db, id=subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    await crud_subject_prompt.upsert(db, subject_id, key, payload.value)
    return _to_out(key, payload.value)


@router.delete("/{subject_id}/prompts/{key}", response_model=SubjectPromptOut)
async def reset_subject_prompt(
    subject_id: int,
    key: str,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """重置为默认：删除该科目的覆盖行。"""
    if key not in SUBJECT_PROMPTS:
        raise HTTPException(status_code=404, detail="Unknown prompt key")
    await crud_subject_prompt.remove(db, subject_id, key)
    return _to_out(key, None)
