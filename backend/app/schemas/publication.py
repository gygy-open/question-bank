from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from enum import Enum
from datetime import datetime

from app.models.publication import PublicationStatus, PublicationType, BlockType


class OutputFormat(str, Enum):
    DOCX = "docx"
    LATEX = "latex"

class ContentPosition(str, Enum):
    """Where to place additional content (answers, explanations, etc.)"""
    AFTER_QUESTION = "after_question"  # Immediately after each question
    END_OF_PAPER = "end_of_paper"      # Unified appendix at the end
    HIDDEN = "hidden"                   # Don't include at all


# --- Export ---

class PublicationExportOptions(BaseModel):
    title: Optional[str] = None
    format: OutputFormat = OutputFormat.DOCX
    content_position: ContentPosition = ContentPosition.AFTER_QUESTION
    include_answer: bool = True
    include_analysis: bool = True
    include_explanation: bool = True
    include_summary: bool = True
    include_source: bool = False


# --- Publication CRUD ---

class PublicationCreate(BaseModel):
    title: str
    pub_type: PublicationType = PublicationType.EXAM_PAPER
    subject_id: Optional[int] = None
    description: Optional[str] = None
    difficulty: Optional[int] = None
    knowledge_point_ids: Optional[List[int]] = None


class PublicationUpdate(BaseModel):
    title: Optional[str] = None
    subject_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[PublicationStatus] = None
    difficulty: Optional[int] = None
    knowledge_point_ids: Optional[List[int]] = None


# --- Blocks ---

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


class BlockWrite(BaseModel):
    block_type: BlockType
    content: Optional[Any] = None
    ref_question_id: Optional[int] = None


class BlocksReplace(BaseModel):
    """整表覆写: 前端提交完整有序块列表。"""
    blocks: List[BlockWrite]


class BlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    block_type: str
    sequence: int
    content: Optional[Any] = None
    ref_question_id: Optional[int] = None
    question: Optional[QuestionBrief] = None


class PublicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pub_type: str
    title: str
    description: Optional[str] = None
    status: str
    difficulty: Optional[int] = None
    subject_id: Optional[int] = None
    owner_id: int
    created_at: datetime
    updated_at: datetime
    block_count: int = 0


class PublicationDetail(PublicationRead):
    blocks: List[BlockRead] = []
    knowledge_point_ids: List[int] = []
