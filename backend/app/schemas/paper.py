from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from enum import Enum
from datetime import datetime

from app.models.paper import PaperStatus

class OutputFormat(str, Enum):
    DOCX = "docx"
    LATEX = "latex"

class PaperGenerateRequest(BaseModel):
    title: str
    question_ids: List[int]
    format: OutputFormat = OutputFormat.DOCX
    include_answer: bool = True
    include_analysis: bool = True
    include_explanation: bool = True
    include_summary: bool = True
    include_source: bool = False


# --- Multi-paper management ---

class PaperExportOptions(BaseModel):
    title: Optional[str] = None
    format: OutputFormat = OutputFormat.DOCX
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
    content: str
    q_type: str
    difficulty: int
    options: Optional[Any] = None
    answer: Optional[str] = None
    thinking: Optional[str] = None
    analysis: Optional[str] = None
    summary: Optional[str] = None


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
