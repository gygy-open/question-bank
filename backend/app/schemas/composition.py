from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from enum import Enum
from datetime import datetime

from app.models.composition import CompositionStatus, CompositionScope, BlockType


class OutputFormat(str, Enum):
    DOCX = "docx"
    LATEX = "latex"


class ContentPosition(str, Enum):
    """Where to place additional content (answers, explanations, etc.)"""
    AFTER_QUESTION = "after_question"  # Immediately after each question
    END_OF_PAPER = "end_of_paper"      # Unified appendix at the end
    HIDDEN = "hidden"                   # Don't include at all


# --- Export ---

class CompositionExportOptions(BaseModel):
    title: Optional[str] = None
    format: OutputFormat = OutputFormat.DOCX
    content_position: ContentPosition = ContentPosition.AFTER_QUESTION
    include_answer: bool = True
    include_analysis: bool = True
    include_explanation: bool = True
    include_summary: bool = True
    include_source: bool = False


# --- Folder ---

class FolderCreate(BaseModel):
    name: str
    kind: str                       # component / deliverable
    subject_id: int
    scope: Optional[str] = None     # deliverable 树: team / personal
    parent_id: Optional[int] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None  # 移动


class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: Optional[int] = None
    kind: str
    scope: Optional[str] = None
    subject_id: int
    owner_id: int
    sequence: Optional[int] = 0


# --- Composition CRUD ---

class CompositionCreate(BaseModel):
    title: str
    comp_type: str = "exam_paper"
    folder_id: Optional[int] = None      # 缺省 -> 解析/创建对应根文件夹
    subject_id: Optional[int] = None     # 无 folder_id 时用于解析根文件夹
    scope: Optional[str] = None          # deliverable 缺省 personal
    description: Optional[str] = None
    difficulty: Optional[int] = None


class CompositionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CompositionStatus] = None
    difficulty: Optional[int] = None
    folder_id: Optional[int] = None      # 移动 (可跨 scope)


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
    ref_composition_id: Optional[int] = None


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
    ref_composition_id: Optional[int] = None
    question: Optional[QuestionBrief] = None


class CompositionRead(BaseModel):
    id: int
    comp_type: str
    kind: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str
    difficulty: Optional[int] = None
    folder_id: int
    subject_id: Optional[int] = None
    scope: Optional[str] = None
    owner_id: int
    created_at: datetime
    updated_at: datetime
    block_count: int = 0


class CompositionDetail(CompositionRead):
    blocks: List[BlockRead] = []
