from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.question import QuestionStatus, QuestionVisibility
from app.schemas.question import QuestionSummary, RichDoc


class StimulusCreate(BaseModel):
    content: RichDoc
    status: QuestionStatus = QuestionStatus.DRAFT
    visibility: QuestionVisibility = QuestionVisibility.PUBLIC
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StimulusUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    content: RichDoc = None
    status: Optional[QuestionStatus] = None
    visibility: Optional[QuestionVisibility] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class StimulusRead(BaseModel):
    id: int
    subject_id: int
    content: RichDoc
    status: str
    visibility: str
    source: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict, serialization_alias="metadata")
    revision: int
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("metadata_json", mode="before")
    @classmethod
    def parse_metadata(cls, value: Any) -> Dict[str, Any]:
        if isinstance(value, str):
            return json.loads(value)
        return value or {}

    class Config:
        from_attributes = True


class QuestionGroupItemInput(BaseModel):
    question_id: int
    position: int = Field(ge=0)


def _validate_items(items: List[QuestionGroupItemInput]) -> None:
    if not items:
        raise ValueError("题组至少包含一道题")
    question_ids = [item.question_id for item in items]
    positions = [item.position for item in items]
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("题组内 question_id 不可重复")
    if len(positions) != len(set(positions)):
        raise ValueError("题组内 position 不可重复")


class QuestionGroupCreate(BaseModel):
    stimulus_id: int
    status: QuestionStatus = QuestionStatus.DRAFT
    visibility: QuestionVisibility = QuestionVisibility.PUBLIC
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    items: List[QuestionGroupItemInput]

    @model_validator(mode="after")
    def validate_items(self) -> "QuestionGroupCreate":
        _validate_items(self.items)
        return self


class QuestionGroupUpdate(BaseModel):
    expected_revision: int = Field(ge=1)
    stimulus_id: Optional[int] = None
    status: Optional[QuestionStatus] = None
    visibility: Optional[QuestionVisibility] = None
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    items: Optional[List[QuestionGroupItemInput]] = None

    @model_validator(mode="after")
    def validate_items(self) -> "QuestionGroupUpdate":
        if self.items is not None:
            _validate_items(self.items)
        return self


class QuestionGroupItemRead(BaseModel):
    question_id: int
    position: int
    question: QuestionSummary

    class Config:
        from_attributes = True


class QuestionGroupRead(BaseModel):
    id: int
    subject_id: int
    stimulus_id: int
    status: str
    visibility: str
    source: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict, serialization_alias="metadata")
    revision: int
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    stimulus: StimulusRead
    items: List[QuestionGroupItemRead]

    @field_validator("metadata_json", mode="before")
    @classmethod
    def parse_metadata(cls, value: Any) -> Dict[str, Any]:
        if isinstance(value, str):
            return json.loads(value)
        return value or {}

    class Config:
        from_attributes = True


class QuestionRelationCreate(BaseModel):
    source_question_id: int
    target_question_id: int