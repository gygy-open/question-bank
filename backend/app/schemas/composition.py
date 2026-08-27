"""组稿 (Composition) 领域 Pydantic schemas —— AST 阶段(node 契约)。

线性 block 契约整体退役,改为 CompositionNode AST 契约:
- 客户端负责生成节点 UUID(``id`` 必填),无 temp_id / id_map 往返。
- ``PUT .../nodes`` 整体替换整棵 AST;``position`` 不由客户端传入,而由请求列表内每个
  ``(parent, slot)`` 分组的顺序在服务层规范化。
- 校验严格按 node_kind / node_type 分派 payload。
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.composition import (
    BLOCK_NODE_TYPES,
    BODY_SLOT,
    CompositionNodeKind,
    CompositionStatus,
    MODULE_NODE_TYPES,
    NODE_TYPE_ANSWER_ITEM,
    NODE_TYPE_HEADING,
    NODE_TYPE_PAGE_BREAK,
    NODE_TYPE_QUESTION,
    NODE_TYPE_QUESTION_DETAILS,
    NODE_TYPE_RICH_TEXT,
    REFERENCE_NODE_TYPES,
    ScopeType,
)
from app.schemas.paper import OutputFormat
from app.schemas.user import User
from app.services.question_content import validate_rich_doc

# question_details 汇总 / answer_item override 涉及的四个可发布字段。
ANSWER_FIELD_KEYS = ("answer", "thinking", "analysis", "summary")
# question_details.props.scope 合法取值。
DETAIL_SCOPE_VALUES = ("before", "all")


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
# CompositionNode —— payload 校验助手
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


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


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


def _validate_heading_props(props: Optional[Dict[str, Any]]) -> None:
    level = (props or {}).get("level")
    if not isinstance(level, int) or isinstance(level, bool) or not (1 <= level <= 4):
        raise ValueError("heading props.level must be an integer in 1..4")
    if set((props or {}).keys()) - {"level"}:
        raise ValueError("heading props may only contain 'level'")


def _validate_question_details_props(props: Optional[Dict[str, Any]]) -> None:
    props = props or {}
    if set(props.keys()) - {"scope", "fields"}:
        raise ValueError("question_details props may only contain 'scope' and 'fields'")
    if props.get("scope") not in DETAIL_SCOPE_VALUES:
        raise ValueError("question_details props.scope must be 'before' or 'all'")
    fields = props.get("fields")
    if not isinstance(fields, dict):
        raise ValueError("question_details props.fields must be an object")
    if set(fields.keys()) != set(ANSWER_FIELD_KEYS):
        raise ValueError(
            "question_details props.fields keys must be exactly "
            f"{ANSWER_FIELD_KEYS}"
        )
    for key, value in fields.items():
        if not isinstance(value, bool):
            raise ValueError(f"question_details props.fields.{key} must be a boolean")


def _validate_question_props(props: Optional[Dict[str, Any]]) -> None:
    if not props:
        return
    if set(props.keys()) - {"number", "show", "optionLayout", "score"}:
        raise ValueError("question props may only contain 'number', 'show', 'optionLayout' and 'score'")
    number = props.get("number")
    if number is not None:
        if not isinstance(number, str):
            raise ValueError("question props.number must be a string")
        if len(number) > 16:
            raise ValueError("question props.number must be at most 16 characters")
    show = props.get("show")
    if show is not None:
        if not isinstance(show, dict):
            raise ValueError("question props.show must be an object")
        if set(show.keys()) - set(ANSWER_FIELD_KEYS):
            raise ValueError(f"question props.show keys must be within {ANSWER_FIELD_KEYS}")
        for key, value in show.items():
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"question props.show.{key} must be boolean or null")
    layout = props.get("optionLayout")
    if layout is not None and (isinstance(layout, bool) or layout not in ("auto", 1, 2, 4)):
        raise ValueError("question props.optionLayout must be one of 'auto', 1, 2, 4")
    score = props.get("score")
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("question props.score must be a number")
        if not (0 <= score <= 1000):
            raise ValueError("question props.score must be between 0 and 1000")


def _validate_answer_item_props(props: Optional[Dict[str, Any]]) -> None:
    props = props or {}
    if set(props.keys()) - {"included", "overrides"}:
        raise ValueError("answer_item props may only contain 'included' and 'overrides'")
    if not isinstance(props.get("included"), bool):
        raise ValueError("answer_item props.included must be a boolean")
    overrides = props.get("overrides")
    if not isinstance(overrides, dict):
        raise ValueError("answer_item props.overrides must be an object")
    if set(overrides.keys()) != set(ANSWER_FIELD_KEYS):
        raise ValueError(
            f"answer_item props.overrides keys must be exactly {ANSWER_FIELD_KEYS}"
        )
    for key, value in overrides.items():
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"answer_item props.overrides.{key} must be boolean or null")


# --------------------------------------------------------------------------- #
# CompositionNode —— 整体替换请求(AST 契约)
# --------------------------------------------------------------------------- #
class CompositionNodeInput(BaseModel):
    """AST 替换里的单个节点。``id`` 为客户端 UUID;``position`` 不由客户端传入。

    question 节点的 ``question_revision`` 与冻结快照由服务端负责,客户端传值被忽略。
    answer_item 的 reference 关系由服务端按 module scope 规范化。
    """
    id: str
    parent_id: Optional[str] = None
    slot: Optional[str] = None
    node_kind: CompositionNodeKind
    node_type: str
    content: Optional[Dict[str, Any]] = None
    props: Optional[Dict[str, Any]] = None
    schema_version: int = 1
    question_id: Optional[int] = None
    source_question_node_id: Optional[str] = None
    anchor_before_node_id: Optional[str] = None

    @model_validator(mode="after")
    def _check(self) -> "CompositionNodeInput":
        if not _is_valid_uuid(self.id):
            raise ValueError("node id must be a valid UUID string")

        kind = self.node_kind
        nt = self.node_type
        # kind ↔ node_type 一致性。
        if kind == CompositionNodeKind.BLOCK and nt not in BLOCK_NODE_TYPES:
            raise ValueError(f"block node_type must be one of {sorted(BLOCK_NODE_TYPES)}")
        if kind == CompositionNodeKind.MODULE and nt not in MODULE_NODE_TYPES:
            raise ValueError(f"module node_type must be one of {sorted(MODULE_NODE_TYPES)}")
        if kind == CompositionNodeKind.REFERENCE and nt not in REFERENCE_NODE_TYPES:
            raise ValueError(f"reference node_type must be one of {sorted(REFERENCE_NODE_TYPES)}")

        # slot ↔ parent 一致性:root(无父)slot 必须为空;子节点 slot 必须为 body。
        if self.parent_id is None:
            if self.slot is not None:
                raise ValueError("root node must not carry a slot")
        else:
            if not _is_valid_uuid(self.parent_id):
                raise ValueError("parent_id must be a valid UUID string")
            if self.slot != BODY_SLOT:
                raise ValueError(f"child node slot must be '{BODY_SLOT}'")

        # question_id / source / anchor 只允许挂在对应节点类型上。
        if nt != NODE_TYPE_QUESTION and self.question_id is not None:
            raise ValueError("question_id is only valid on question nodes")
        if nt != NODE_TYPE_ANSWER_ITEM and self.source_question_node_id is not None:
            raise ValueError("source_question_node_id is only valid on answer_item nodes")
        if nt == NODE_TYPE_ANSWER_ITEM and self.anchor_before_node_id is not None:
            raise ValueError("answer_item nodes must not carry anchor_before_node_id")
        if self.anchor_before_node_id is not None and not _is_valid_uuid(self.anchor_before_node_id):
            raise ValueError("anchor_before_node_id must be a valid UUID string")

        # 层级归属约束(跨节点的“父必须是同稿 module”留给服务层):
        if nt in (NODE_TYPE_QUESTION, NODE_TYPE_PAGE_BREAK, NODE_TYPE_QUESTION_DETAILS):
            if self.parent_id is not None:
                raise ValueError(f"{nt} must be a root-level node")
        if nt == NODE_TYPE_ANSWER_ITEM and self.parent_id is None:
            raise ValueError("answer_item must live inside a question_details module")

        # 分类型 payload 校验。
        if nt == NODE_TYPE_RICH_TEXT:
            _require_nonempty_rich_doc(self.content, label="rich_text")
            if self.props:
                raise ValueError("rich_text nodes must not carry props")
        elif nt == NODE_TYPE_HEADING:
            _require_single_paragraph_doc(self.content)
            _validate_heading_props(self.props)
        elif nt == NODE_TYPE_QUESTION:
            if self.content is not None:
                raise ValueError("question node content must be null (frozen by server)")
            _validate_question_props(self.props)
            if self.question_id is None:
                raise ValueError("question node requires question_id")
        elif nt == NODE_TYPE_PAGE_BREAK:
            if self.content is not None or self.props is not None:
                raise ValueError("page_break node must not carry content or props")
        elif nt == NODE_TYPE_QUESTION_DETAILS:
            if self.content is not None:
                raise ValueError("question_details node content must be null")
            _validate_question_details_props(self.props)
        elif nt == NODE_TYPE_ANSWER_ITEM:
            if self.content is not None:
                raise ValueError("answer_item node content must be null")
            if self.source_question_node_id is None:
                raise ValueError("answer_item requires source_question_node_id")
            _validate_answer_item_props(self.props)
        return self


class CompositionNodesReplaceRequest(BaseModel):
    expected_revision: int
    batch_id: Optional[str] = None
    nodes: List[CompositionNodeInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_ids(self) -> "CompositionNodesReplaceRequest":
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("node id values must be unique within a batch")
        return self


class CompositionNodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    composition_id: int
    parent_id: Optional[str] = None
    slot: Optional[str] = None
    position: int
    node_kind: CompositionNodeKind
    node_type: str
    content: Optional[Dict[str, Any]] = None
    props: Optional[Dict[str, Any]] = None
    schema_version: int
    question_id: Optional[int] = None
    question_revision: Optional[int] = None
    source_question_node_id: Optional[str] = None
    anchor_before_node_id: Optional[str] = None


class CompositionNodesReplaceResponse(BaseModel):
    revision: int
    nodes: List[CompositionNodeRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Question node 版本状态 / 同步(冻结快照)契约
# --------------------------------------------------------------------------- #
class QuestionRevisionStatus(BaseModel):
    """稿件内某 question_id 的实时 revision 状态(仅状态,不含题目内容)。

    available=False 表示实时题目缺失或已软删除;此时 current_revision 为 None。
    """
    question_id: int
    current_revision: Optional[int] = None
    available: bool


class CompositionQuestionNodesSyncRequest(BaseModel):
    """同步请求:expected_revision 乐观校验,node_ids 为要刷新的 question 节点(唯一非空)。

    "同步此题" 传单个 id,"同步全部" 传全部 question 节点 id,契约一致。
    """
    expected_revision: int
    node_ids: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_node_ids(self) -> "CompositionQuestionNodesSyncRequest":
        if not self.node_ids:
            raise ValueError("node_ids must not be empty")
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("node_ids must be unique")
        return self


class CompositionQuestionNodesSyncResponse(BaseModel):
    """同步响应:自增后的 revision + 刷新后的完整 node 序列(供前端 reconcile)。"""
    revision: int
    nodes: List[CompositionNodeRead] = Field(default_factory=list)


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
    numbering_enabled: Optional[bool] = None
    scoring_enabled: Optional[bool] = None
    question_display: Optional[Dict[str, bool]] = None


class CompositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    status: str
    revision: int
    numbering_enabled: bool = False
    scoring_enabled: bool = False
    question_display: Dict[str, bool] = Field(default_factory=lambda: {k: False for k in ANSWER_FIELD_KEYS})
    scope_type: ScopeType
    owner_id: Optional[int] = None
    subject_id: int
    folder_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None

    @field_validator("question_display", mode="before")
    @classmethod
    def _normalize_question_display(cls, v: Any) -> Dict[str, bool]:
        # NULL / 部分 map 均补全为四字段（缺省 false）。
        return {k: bool(v.get(k, False)) if isinstance(v, dict) else False for k in ANSWER_FIELD_KEYS}


class CompositionDetail(CompositionRead):
    nodes: List[CompositionNodeRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Version snapshot 构件
# --------------------------------------------------------------------------- #
class QuestionContentSnapshot(BaseModel):
    """冻结在 question 节点上的题目内容快照(不含 id/revision)。

    id 由 node.question_id 承载、revision 由 node.question_revision 承载,故此处不重复。
    difficulty/source 一并冻结,但它们单独变化不触发 Question.content_revision。
    """
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


class QuestionSnapshot(BaseModel):
    """定稿时冻结的题目内容投影(snapshot v2 内 question 节点)。

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


class CompositionExportRequest(BaseModel):
    """版本导出请求体:format 决定渲染器,title 可选覆盖导出文件里的标题。"""
    format: OutputFormat
    title: Optional[str] = None


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
    actor: Optional[User] = None
    created_at: datetime


class CompositionEventPage(BaseModel):
    items: List[CompositionEventRead]
    has_more: bool
