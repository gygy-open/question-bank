from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import models
from app.api import deps
from app.core.permissions import Permission
from app.crud.crud_subject import subject as crud_subject
from app.crud.crud_subject_setting import subject_setting as crud_subject_setting
from app.schemas.composition import ANSWER_SPACE_MAX_LINES, ANSWER_SPACE_STYLES
from app.services.answer_space import (
    DEFAULT_RULES,
    SUBJECT_SETTING_KEY,
    merge_rules,
    rules_to_payload,
)

router = APIRouter()


class AnswerSpaceRuleIn(BaseModel):
    enabled: bool
    min_lines: int = Field(ge=1, le=ANSWER_SPACE_MAX_LINES)
    lines_per_score: float = Field(ge=0)
    max_lines: int = Field(ge=1, le=ANSWER_SPACE_MAX_LINES)
    style: str

    def _check_style(self) -> None:
        if self.style not in ANSWER_SPACE_STYLES:
            raise ValueError(f"style must be one of {ANSWER_SPACE_STYLES}")


class AnswerSpaceRulesOut(BaseModel):
    rules: Dict[str, Dict[str, Any]]
    defaults: Dict[str, Dict[str, Any]]
    is_custom: bool


class AnswerSpaceRulesUpdate(BaseModel):
    rules: Dict[str, AnswerSpaceRuleIn]


async def _require_subject(db: Any, subject_id: int) -> None:
    if not await crud_subject.get(db, id=subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")


def _out(override: Any) -> AnswerSpaceRulesOut:
    return AnswerSpaceRulesOut(
        rules=rules_to_payload(merge_rules(override)),
        defaults=rules_to_payload(DEFAULT_RULES),
        is_custom=override is not None,
    )


@router.get("/{subject_id}/answer-space-rules", response_model=AnswerSpaceRulesOut)
async def get_answer_space_rules(
    subject_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """返回该学科生效的作答区推导规则，以及代码默认值与是否已定制。"""
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    override = await crud_subject_setting.get_value(db, subject_id, SUBJECT_SETTING_KEY)
    return _out(override)


@router.put("/{subject_id}/answer-space-rules", response_model=AnswerSpaceRulesOut)
async def update_answer_space_rules(
    subject_id: int,
    payload: AnswerSpaceRulesUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """保存该学科的作答区规则覆盖。未知题型键被忽略，非法字段回退到代码默认值。"""
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.MANAGE_SUBJECT, subject_id=subject_id)
    for rule in payload.rules.values():
        rule._check_style()
        if rule.max_lines < rule.min_lines:
            raise HTTPException(status_code=422, detail="max_lines must be >= min_lines")
    override = {
        q_type: rule.model_dump()
        for q_type, rule in payload.rules.items()
        if q_type in DEFAULT_RULES
    }
    await crud_subject_setting.upsert(db, subject_id, SUBJECT_SETTING_KEY, override)
    return _out(override)


@router.delete("/{subject_id}/answer-space-rules", response_model=AnswerSpaceRulesOut)
async def reset_answer_space_rules(
    subject_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """清除覆盖，回到代码默认值。"""
    await _require_subject(db, subject_id)
    deps.require(current_user, Permission.MANAGE_SUBJECT, subject_id=subject_id)
    await crud_subject_setting.remove(db, subject_id, SUBJECT_SETTING_KEY)
    return _out(None)
