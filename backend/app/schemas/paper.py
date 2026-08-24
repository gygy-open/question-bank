from pydantic import BaseModel, ConfigDict, field_validator
from typing import List, Optional, Any
from enum import Enum
from datetime import datetime

from app.models.paper import PaperStatus
from app.services.question_content import parse_json_field
from app.schemas.question import AnswerSpec, Option, RichDoc

class OutputFormat(str, Enum):
    DOCX = "docx"
    LATEX = "latex"

class ContentPosition(str, Enum):
    """Where to place additional content (answers, explanations, etc.)"""
    AFTER_QUESTION = "after_question"  # Immediately after each question
    END_OF_PAPER = "end_of_paper"      # Unified appendix at the end
    HIDDEN = "hidden"                   # Don't include at all


# --- Multi-paper management ---

class PaperExportOptions(BaseModel):
    title: Optional[str] = None
    format: OutputFormat = OutputFormat.DOCX
    content_position: ContentPosition = ContentPosition.AFTER_QUESTION
    include_answer: bool = True
    include_analysis: bool = True
    include_explanation: bool = True
    include_summary: bool = True
    include_source: bool = False


class PaperCreate(BaseModel):
    title: str
    subject_id: Optional[int] = None
    description: Optional[str] = None


class PaperUpdate(BaseModel):
    title: Optional[str] = None
    subject_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[PaperStatus] = None


class PaperItemsAdd(BaseModel):
    question_ids: List[int]


class PaperReorder(BaseModel):
    ordered_item_ids: List[int]


class PaperItemUpdate(BaseModel):
    section_title: Optional[str] = None
    score: Optional[float] = None


class QuestionBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: RichDoc = None
    q_type: str
    difficulty: int
    options: Optional[List[Option]] = None
    answer: Optional[AnswerSpec] = None
    thinking: RichDoc = None
    analysis: RichDoc = None
    summary: RichDoc = None

    @field_validator("answer", mode="before")
    @classmethod
    def _parse_answer(cls, v: Any) -> Any:
        return parse_json_field(v)


class PaperItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question_id: int
    sequence: int
    section_title: Optional[str] = None
    score: Optional[float] = None
    question: Optional[QuestionBrief] = None


class PaperRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    status: str
    subject_id: Optional[int] = None
    owner_id: int
    created_at: datetime
    updated_at: datetime
    question_count: int = 0


class PaperDetail(PaperRead):
    items: List[PaperItemRead] = []
