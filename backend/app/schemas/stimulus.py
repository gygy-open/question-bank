from datetime import datetime
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.question import QuestionStatus, QuestionVisibility
from app.schemas.question import QuestionCreate, QuestionSummary, QuestionUpdate, RichDoc


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


class RestoreRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class StimulusQuestionsUpdate(BaseModel):
    """整体设置材料下的有序小题;未列出的现有小题解除与材料的关联。"""

    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    question_ids: List[int]

    @field_validator("question_ids")
    @classmethod
    def _unique(cls, value: List[int]) -> List[int]:
        if len(value) != len(set(value)):
            raise ValueError("question_ids 不可重复")
        return value


class StimulusBundleQuestion(BaseModel):
    """整体保存中的一道小题:无 id 时按 create 新建;有 id 时保留该题,可附带 update。"""

    model_config = ConfigDict(extra="forbid")

    id: Optional[int] = None
    create: Optional[QuestionCreate] = None
    update: Optional[QuestionUpdate] = None

    @model_validator(mode="after")
    def _shape(self) -> "StimulusBundleQuestion":
        if self.id is None and (self.create is None or self.update is not None):
            raise ValueError("新小题必须且只能提供 create")
        if self.id is not None and self.create is not None:
            raise ValueError("已有小题不能提供 create")
        return self


class StimulusBundleCreate(BaseModel):
    """材料与有序小题在同一事务内保存;未列出的现有小题解除与材料的关联。"""

    model_config = ConfigDict(extra="forbid")

    content: RichDoc
    status: QuestionStatus = QuestionStatus.DRAFT
    visibility: QuestionVisibility = QuestionVisibility.PUBLIC
    source: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    questions: List[StimulusBundleQuestion] = Field(default_factory=list)

    @field_validator("questions")
    @classmethod
    def _unique_ids(cls, value: List[StimulusBundleQuestion]) -> List[StimulusBundleQuestion]:
        ids = [item.id for item in value if item.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("小题不可重复")
        return value


class StimulusBundleUpdate(StimulusBundleCreate):
    expected_revision: int = Field(ge=1)


class StimulusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    content: RichDoc
    status: str
    visibility: str
    source: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict, serialization_alias="metadata")
    revision: int
    content_revision: int
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    @field_validator("metadata_json", mode="before")
    @classmethod
    def parse_metadata(cls, value: Any) -> Dict[str, Any]:
        if isinstance(value, str):
            return json.loads(value)
        return value or {}


class StimulusDetail(StimulusRead):
    questions: List[QuestionSummary] = Field(default_factory=list)


class StimulusListItem(StimulusRead):
    question_count: int = 0


class StimulusPage(BaseModel):
    items: List[StimulusListItem]
    total: int
    page: int
    size: int
    pages: int
