from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from enum import Enum
from datetime import datetime

from app.models.composition import CompositionStatus, FolderScope, BlockType


class OutputFormat(str, Enum):
    DOCX = "docx"
    LATEX = "latex"


# --- Export ---

class CompositionExportOptions(BaseModel):
    title: Optional[str] = None
    format: OutputFormat = OutputFormat.DOCX


# --- Folder ---

class FolderCreate(BaseModel):
    name: str
    subject_id: int
    scope: FolderScope = FolderScope.PERSONAL
    parent_id: Optional[int] = None


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None  # 移动


class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    parent_id: Optional[int] = None
    subject_id: int
    owner_id: int
    scope: str
    sequence: Optional[int] = 0


# --- Composition CRUD ---

class CompositionCreate(BaseModel):
    title: str
    folder_id: Optional[int] = None      # 缺省 -> 解析/创建对应根文件夹
    subject_id: Optional[int] = None     # 无 folder_id 时用于解析根文件夹
    scope: FolderScope = FolderScope.PERSONAL  # 无 folder_id 时用于解析根文件夹归属空间
    description: Optional[str] = None
    difficulty: Optional[int] = None
    meta_data: Optional[Any] = None      # 文档级设置: show_answers / answer_position 等


class CompositionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CompositionStatus] = None
    difficulty: Optional[int] = None
    folder_id: Optional[int] = None      # 移动 (可跨 scope)
    meta_data: Optional[Any] = None      # 文档级设置


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
    source: Optional[str] = None


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


class CompositionRead(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    is_template: bool = False
    difficulty: Optional[int] = None
    meta_data: Optional[Any] = None
    folder_id: int
    subject_id: Optional[int] = None
    scope: Optional[str] = None
    owner_id: int
    created_at: datetime
    updated_at: datetime
    block_count: int = 0


class CompositionDetail(CompositionRead):
    blocks: List[BlockRead] = []


# --- Templates ---

class TemplateItem(BaseModel):
    """新建时的起点: 系统预置 (source=system, key 为硬编码标识) 或自定义 (source=custom, id 为组稿 id)。"""
    source: str                      # "system" | "custom"
    key: Optional[str] = None        # system 模板标识
    id: Optional[int] = None         # custom 模板对应的 composition id
    label: str
    icon: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[str] = None      # custom: personal / team


class CreateFromTemplate(BaseModel):
    """从模板新建: 系统模板给 key, 自定义模板给 template_id。"""
    source: str = "system"           # "system" | "custom"
    key: Optional[str] = None
    template_id: Optional[int] = None
    title: Optional[str] = None
    folder_id: Optional[int] = None
    subject_id: Optional[int] = None
    scope: FolderScope = FolderScope.PERSONAL


class SaveAsTemplate(BaseModel):
    """将现有文档另存为自定义模板。"""
    title: Optional[str] = None
    scope: FolderScope = FolderScope.PERSONAL
