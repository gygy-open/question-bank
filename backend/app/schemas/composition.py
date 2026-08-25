"""组稿 (Composition) 领域 Pydantic schemas —— 第一阶段。

仅提供 create/update/read 数据契约;CRUD 与 API endpoint 留待下一阶段,避免半成品接口。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.composition import (
    CompositionBlockType,
    CompositionStatus,
    ScopeType,
)
from app.services.question_content import validate_rich_doc


def _validate_scope_owner(scope_type: ScopeType, owner_id: Optional[int]) -> None:
    """镜像数据库 CheckConstraint:shared→owner 必须为空,personal→owner 必填。"""
    if scope_type == ScopeType.SHARED and owner_id is not None:
        raise ValueError("shared scope must not carry an owner_id")
    if scope_type == ScopeType.PERSONAL and owner_id is None:
        raise ValueError("personal scope requires an owner_id")


# --------------------------------------------------------------------------- #
# Folder
# --------------------------------------------------------------------------- #
class FolderCreate(BaseModel):
    name: str
    scope_type: ScopeType
    subject_id: int
    owner_id: Optional[int] = None
    parent_id: Optional[int] = None

    @model_validator(mode="after")
    def _check_scope(self) -> "FolderCreate":
        _validate_scope_owner(self.scope_type, self.owner_id)
        return self


class FolderUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None


class FolderCreateRequest(BaseModel):
    """API 请求体:scope/subject/owner 均由路径与鉴权强制,客户端不可指定。"""
    name: str
    parent_id: Optional[int] = None


class FolderUpdateRequest(BaseModel):
    """parent_id 允许显式置空(移到根);用 model_fields_set 区分未提供与置空。"""
    name: Optional[str] = None
    parent_id: Optional[int] = None


class FolderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    scope_type: ScopeType
    owner_id: Optional[int] = None
    subject_id: int
    parent_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------- #
# CompositionBlock
# --------------------------------------------------------------------------- #
class CompositionBlockBase(BaseModel):
    block_type: CompositionBlockType
    content: Optional[Dict[str, Any]] = None
    props: Optional[Dict[str, Any]] = None
    schema_version: int = 1
    question_id: Optional[int] = None
    question_revision: Optional[int] = None

    @model_validator(mode="after")
    def _check_question_ref(self) -> "CompositionBlockBase":
        # 镜像 ck_composition_blocks_question_ref_matches_type:
        # question block 必须同时携带 question_id 与 question_revision;其余 block 均不得携带。
        if self.block_type == CompositionBlockType.QUESTION:
            if self.question_id is None or self.question_revision is None:
                raise ValueError(
                    "question blocks require both question_id and question_revision"
                )
        elif self.question_id is not None or self.question_revision is not None:
            raise ValueError(
                "question_id/question_revision are only valid on question blocks"
            )
        return self


class CompositionBlockCreate(CompositionBlockBase):
    sequence: int


class CompositionBlockRead(CompositionBlockBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    composition_id: int
    sequence: int


# --------------------------------------------------------------------------- #
# CompositionBlock 批量替换请求(画布契约)
# --------------------------------------------------------------------------- #
# 允许出现在 heading 段落内的行内叶子节点集合;凡带非空 content 的子节点都视为块级嵌套。
_HEADING_BLOCK_NODE_TYPES = {
    "paragraph",
    "heading",
    "bulletList",
    "orderedList",
    "listItem",
    "blockquote",
    "codeBlock",
    "table",
    "tableRow",
    "tableCell",
}


def _require_nonempty_rich_doc(content: Any, *, label: str) -> None:
    doc = validate_rich_doc(content)
    if not doc or not (doc.get("content") or []):
        raise ValueError(f"{label} content must be a non-empty RichDoc")


def _require_single_paragraph_doc(content: Any) -> None:
    doc = validate_rich_doc(content)
    if doc is None:
        raise ValueError("heading content is required")
    children = doc.get("content") or []
    if len(children) != 1 or not isinstance(children[0], dict) or children[0].get("type") != "paragraph":
        raise ValueError("heading content must be a single paragraph")
    for node in children[0].get("content") or []:
        if not isinstance(node, dict):
            continue
        if node.get("type") in _HEADING_BLOCK_NODE_TYPES or (node.get("content") or []):
            raise ValueError("heading paragraph must contain only inline content")


class CompositionBlockReplaceItem(BaseModel):
    """批量替换的单个 block。顺序即 sequence(客户端不得传 sequence)。

    已有 block 带 ``id``,新 block 带唯一 ``temp_id``,二者必须且只能有一个。
    question block 的 ``question_revision`` 由服务端根据数据库钉住,客户端传值被忽略。
    """
    id: Optional[int] = None
    temp_id: Optional[str] = None
    block_type: CompositionBlockType
    content: Optional[Dict[str, Any]] = None
    props: Optional[Dict[str, Any]] = None
    schema_version: int = 1
    question_id: Optional[int] = None
    question_revision: Optional[int] = None

    def _reject_question_ref(self) -> None:
        if self.question_id is not None or self.question_revision is not None:
            raise ValueError(
                f"{self.block_type.value} blocks must not carry question_id/question_revision"
            )

    @model_validator(mode="after")
    def _check(self) -> "CompositionBlockReplaceItem":
        has_id = self.id is not None
        has_temp = self.temp_id is not None and self.temp_id != ""
        if has_id == has_temp:
            raise ValueError("each block must carry exactly one of id or temp_id")

        bt = self.block_type
        if bt == CompositionBlockType.RICH_TEXT:
            _require_nonempty_rich_doc(self.content, label="rich_text")
            if self.props:
                raise ValueError("rich_text blocks must not carry props")
            self._reject_question_ref()
        elif bt == CompositionBlockType.HEADING:
            _require_single_paragraph_doc(self.content)
            level = (self.props or {}).get("level")
            if not isinstance(level, int) or isinstance(level, bool) or not (1 <= level <= 4):
                raise ValueError("heading props.level must be an integer in 1..4")
            if set((self.props or {}).keys()) - {"level"}:
                raise ValueError("heading props may only contain 'level'")
            self._reject_question_ref()
        elif bt == CompositionBlockType.QUESTION:
            if self.content is not None:
                raise ValueError("question block content must be null")
            if self.props:
                raise ValueError("question block props must be empty for now")
            if self.question_id is None:
                raise ValueError("question block requires question_id")
        elif bt == CompositionBlockType.PAGE_BREAK:
            if self.content is not None or self.props is not None:
                raise ValueError("page_break block must not carry content or props")
            self._reject_question_ref()
        elif bt == CompositionBlockType.ANSWER_SUMMARY:
            if self.content is not None:
                raise ValueError("answer_summary content must be null")
            mode = (self.props or {}).get("mode")
            if mode not in ("all", "before"):
                raise ValueError("answer_summary props.mode must be 'all' or 'before'")
            if set((self.props or {}).keys()) - {"mode"}:
                raise ValueError("answer_summary props may only contain 'mode'")
            self._reject_question_ref()
        return self


class CompositionBlocksReplaceRequest(BaseModel):
    expected_revision: int
    batch_id: Optional[str] = None
    blocks: List[CompositionBlockReplaceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_temp_ids(self) -> "CompositionBlocksReplaceRequest":
        temp_ids = [b.temp_id for b in self.blocks if b.temp_id]
        if len(temp_ids) != len(set(temp_ids)):
            raise ValueError("temp_id values must be unique within a batch")
        ids = [b.id for b in self.blocks if b.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("block id values must be unique within a batch")
        return self


class CompositionBlocksReplaceResponse(BaseModel):
    revision: int
    id_map: Dict[str, int] = Field(default_factory=dict)
    blocks: List[CompositionBlockRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #
class CompositionCreate(BaseModel):
    title: str
    scope_type: ScopeType
    subject_id: int
    owner_id: Optional[int] = None
    description: Optional[str] = None
    folder_id: Optional[int] = None

    @model_validator(mode="after")
    def _check_scope(self) -> "CompositionCreate":
        _validate_scope_owner(self.scope_type, self.owner_id)
        return self


class CompositionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CompositionStatus] = None
    folder_id: Optional[int] = None


class CompositionCreateRequest(BaseModel):
    """API 请求体:scope/subject/owner 均由路径与鉴权强制,客户端不可指定。"""
    title: str
    description: Optional[str] = None
    folder_id: Optional[int] = None


class CompositionMetaUpdateRequest(BaseModel):
    """元数据更新;expected_revision 用于乐观锁。folder_id 可显式置空(移出目录)。"""
    expected_revision: int
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CompositionStatus] = None
    folder_id: Optional[int] = None


class CompositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    status: str
    revision: int
    scope_type: ScopeType
    owner_id: Optional[int] = None
    subject_id: int
    folder_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class CompositionDetail(CompositionRead):
    blocks: List[CompositionBlockRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Version snapshot 构件
# --------------------------------------------------------------------------- #
class QuestionSnapshot(BaseModel):
    """定稿时冻结的题目内容投影(snapshot v1)。

    只含可发布内容,排除关系(标签/知识点/创建人)、权限与审核字段。所有富文本槽位
    以原生 JSON(dict/list)存储,由服务层用 parse_json_field 从 ORM JSON 字符串解出后构造。
    """
    id: int
    content_revision: int
    content_schema_version: int
    q_type: str
    content: Optional[Dict[str, Any]] = None
    options: Optional[List[Dict[str, Any]]] = None
    answer: Optional[Dict[str, Any]] = None
    thinking: Optional[Dict[str, Any]] = None
    analysis: Optional[Dict[str, Any]] = None
    summary: Optional[Dict[str, Any]] = None
    difficulty: int
    source: Optional[str] = None


class CompositionVersionCreateRequest(BaseModel):
    """定稿请求体:expected_revision 乐观校验(不修改 revision),label 可选备注。"""
    expected_revision: int
    label: Optional[str] = None


# --------------------------------------------------------------------------- #
# Version / Event (只读投影)
# --------------------------------------------------------------------------- #
class CompositionVersionSummary(BaseModel):
    """版本列表项:不含 snapshot,避免列表响应携带整稿快照。"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    composition_id: int
    version_no: int
    source_revision: int
    title: str
    subject_id: int
    label: Optional[str] = None
    finalized_at: datetime
    finalized_by: int


class CompositionVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    composition_id: int
    version_no: int
    source_revision: int
    title: str
    subject_id: int
    snapshot: Dict[str, Any]
    label: Optional[str] = None
    finalized_at: datetime
    finalized_by: int


class CompositionEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    composition_id: int
    composition_revision: int
    event_type: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    summary: str
    payload: Optional[Dict[str, Any]] = None
    batch_id: Optional[str] = None
    actor_id: int
    created_at: datetime
