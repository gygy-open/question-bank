from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.knowledge_point import KnowledgePoint
from app.schemas.question import RichDoc


class QuestionRelationCreate(BaseModel):
    target_question_id: int


class QuestionRelationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_question_id: int
    target_question_id: int
    relation_type: str
    created_at: datetime
    created_by: Optional[int] = None


class QuestionRelationQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: Optional[int] = None
    content: RichDoc
    q_type: str
    knowledge_points: List[KnowledgePoint] = Field(default_factory=list)


class QuestionRelationPeerRead(BaseModel):
    relation_id: int
    relation_type: str
    question: QuestionRelationQuestionRead
    created_at: datetime
    created_by: Optional[int] = None


class QuestionRelationsRead(BaseModel):
    question_id: int
    sources: List[QuestionRelationPeerRead] = Field(default_factory=list)
    targets: List[QuestionRelationPeerRead] = Field(default_factory=list)
