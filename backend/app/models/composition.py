"""组稿 (Composition) 领域模型 —— AST 阶段。

设计要点(与已确认 ADR 对齐):
- 不建 spaces/space_members 表。Folder / Composition 直接持久化 scope_type + owner_id:
  shared → owner_id 为 NULL;personal → owner_id 非 NULL(由 CheckConstraint 保证)。
- Subject 是强上下文:folders / compositions 的 subject_id 均 NOT NULL。
- CompositionNode 取代线性 CompositionBlock,承载一棵组稿 AST:
  * 主键为客户端生成的 String(36) UUID —— 跨 SQLite/MySQL 稳定,免自增/回填。
  * parent_id 自引用(真 FK,ondelete CASCADE):root 节点 parent 为 NULL;module 子节点
    parent 指向所属 module。首期 module 不嵌套(只有 root / module.body 两层)。
  * slot:root 节点为 NULL;module 子节点为 "body"。
  * position:同一 (parent, slot) 下的 0-based 顺序。
  * node_kind:block / module / reference;node_type:细分类型字符串。
  * source_question_node_id / anchor_before_node_id 为“软指针”:只在服务层保证同稿引用
    (不建 DB FK),避免自引用 FK 的 circular DDL 与插入顺序难题。
- Module Definition / Preset 不入库(纯前端/服务层配置)。
- composition_versions 存不可变 snapshot JSON;composition_events 独立于 activity_logs。
"""
import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
)
from sqlalchemy.orm import relationship

from .base import Base

# BigInteger 供 MySQL 大容量自增 PK;SQLite 仅对 INTEGER PRIMARY KEY 做 rowid 自增,
# 故在 SQLite(桌面版/测试)上退化为 INTEGER 以保留自增语义(仅 events 使用)。
_BigIntPK = BigInteger().with_variant(Integer(), "sqlite")

# 组稿 AST 节点主键:客户端生成的 UUID 文本(str(uuid4()) → 36 字符)。
NODE_ID_LEN = 36

# module 子节点唯一的 slot 名。
BODY_SLOT = "body"


class ScopeType(str, enum.Enum):
    """归属范围:共享(团队可见)或个人私有。"""
    SHARED = "shared"
    PERSONAL = "personal"


class CompositionStatus(str, enum.Enum):
    DRAFT = "draft"
    ARCHIVED = "archived"


class CompositionNodeKind(str, enum.Enum):
    """AST 节点大类。"""
    BLOCK = "block"
    MODULE = "module"
    REFERENCE = "reference"


# node_type 细分(存 String(64),由 schema/service 校验取值合法性)。
NODE_TYPE_RICH_TEXT = "rich_text"
NODE_TYPE_HEADING = "heading"
NODE_TYPE_QUESTION = "question"
NODE_TYPE_PAGE_BREAK = "page_break"
NODE_TYPE_ANSWER_SPACE = "answer_space"
NODE_TYPE_QUESTION_DETAILS = "question_details"
NODE_TYPE_ANSWER_ITEM = "answer_item"

# 各 kind 允许的 node_type 集合(服务层/契约共享)。
BLOCK_NODE_TYPES = frozenset(
    {
        NODE_TYPE_RICH_TEXT,
        NODE_TYPE_HEADING,
        NODE_TYPE_QUESTION,
        NODE_TYPE_PAGE_BREAK,
        NODE_TYPE_ANSWER_SPACE,
    }
)
MODULE_NODE_TYPES = frozenset({NODE_TYPE_QUESTION_DETAILS})
REFERENCE_NODE_TYPES = frozenset({NODE_TYPE_ANSWER_ITEM})


def _enum_col(enum_cls: type[enum.Enum]) -> Enum:
    """按仓库惯例:以 value(而非 name)持久化枚举。"""
    return Enum(enum_cls, values_callable=lambda obj: [e.value for e in obj])


class Folder(Base):
    """组稿文件夹:支持父子层级,承载 scope/owner/subject 上下文。"""
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)

    scope_type = Column(_enum_col(ScopeType), nullable=False)
    # shared → NULL;personal → 非 NULL(由 ck_folders_scope_owner 保证)。
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)
    # Subject 为强上下文。
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)

    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    owner = relationship("User", foreign_keys=[owner_id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    subject = relationship("Subject")
    children = relationship(
        "Folder",
        backref="parent",
        remote_side=[id],
        # 单向:此处仅声明父子导航,子->父由 backref 提供。
    )
    compositions = relationship("Composition", back_populates="folder")

    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'shared' AND owner_id IS NULL) OR "
            "(scope_type = 'personal' AND owner_id IS NOT NULL)",
            name="scope_owner",
        ),
        Index("ix_folders_subject_scope_owner", "subject_id", "scope_type", "owner_id"),
        # 注意:父子文件夹之间 subject/scope/owner 必须一致,但该不变量跨行、无法用简单
        # 行级 CheckConstraint 表达。此处不伪造数据库保证,改由服务层强制。
    )


class Composition(Base):
    """组稿:一份可编辑的稿件,由一棵节点 AST 组成,可产生不可变版本快照。"""
    __tablename__ = "compositions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=CompositionStatus.DRAFT.value, nullable=False)
    revision = Column(Integer, default=1, nullable=False)
    # 题号开关:关闭仅隐藏显示,题号仍保留在 question 节点 props.number 上。
    numbering_enabled = Column(Boolean, nullable=False, default=False, server_default=false())
    # 赋分开关:仅在 numbering_enabled 为真时可开启;关闭仅隐藏显示,分值仍保留在 question 节点 props.score 上。
    scoring_enabled = Column(Boolean, nullable=False, default=False, server_default=false())
    # 画布题目全局显示字段(answer/thinking/analysis/summary);NULL 视为全部隐藏。
    question_display = Column(JSON, nullable=True)

    scope_type = Column(_enum_col(ScopeType), nullable=False)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    owner = relationship("User", foreign_keys=[owner_id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    subject = relationship("Subject")
    folder = relationship("Folder", back_populates="compositions")

    # passive_deletes:节点删除依赖 DB 的 ON DELETE CASCADE(含自引用),ORM 不逐行删,
    # 避免自引用父子删除顺序问题(需 SQLite PRAGMA foreign_keys=ON 生效)。
    nodes = relationship(
        "CompositionNode",
        back_populates="composition",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CompositionNode.position",
    )
    versions = relationship(
        "CompositionVersion",
        back_populates="composition",
        cascade="all, delete-orphan",
        order_by="CompositionVersion.version_no",
    )
    events = relationship(
        "CompositionEvent",
        back_populates="composition",
        cascade="all, delete-orphan",
        order_by="CompositionEvent.created_at",
    )

    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'shared' AND owner_id IS NULL) OR "
            "(scope_type = 'personal' AND owner_id IS NOT NULL)",
            name="scope_owner",
        ),
        Index("ix_compositions_subject_scope_owner", "subject_id", "scope_type", "owner_id"),
    )


class CompositionNode(Base):
    """组稿 AST 的一个节点(block / module / reference)。"""
    __tablename__ = "composition_nodes"

    # 客户端生成的 UUID 文本主键。
    id = Column(String(NODE_ID_LEN), primary_key=True)
    composition_id = Column(
        Integer, ForeignKey("compositions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 自引用父指针(真 FK,ondelete CASCADE):root 节点为 NULL。
    parent_id = Column(
        String(NODE_ID_LEN),
        ForeignKey("composition_nodes.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    slot = Column(String(32), nullable=True)  # root=NULL;module 子节点="body"
    position = Column(Integer, nullable=False)  # 同 (parent, slot) 内 0-based 顺序

    node_kind = Column(_enum_col(CompositionNodeKind), nullable=False)
    node_type = Column(String(64), nullable=False)

    # 结构化内容:rich_text/heading 存 RichDoc;question 存冻结的题目内容快照;其余为 NULL。
    content = Column(JSON, nullable=True)
    props = Column(JSON, nullable=True)
    schema_version = Column(Integer, default=1, nullable=False)

    # 仅 question 节点使用:引用题目及被钉住的修订号。
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True, index=True)
    question_revision = Column(Integer, nullable=True)

    # 软指针(无 DB FK,服务层保证同稿):
    # - reference.answer_item.source_question_node_id → 同稿 root 层 question 节点。
    # - 自定义 module 子节点.anchor_before_node_id → 同 module 内 answer_item 节点。
    source_question_node_id = Column(String(NODE_ID_LEN), nullable=True)
    anchor_before_node_id = Column(String(NODE_ID_LEN), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    composition = relationship("Composition", back_populates="nodes")
    question = relationship("Question")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    __table_args__ = (
        CheckConstraint("position >= 0", name="position_non_negative"),
        CheckConstraint(
            "(parent_id IS NULL AND slot IS NULL) OR "
            "(parent_id IS NOT NULL AND slot = 'body')",
            name="parent_slot_matches",
        ),
        CheckConstraint(
            "(node_kind = 'block' AND node_type IN "
            "('rich_text', 'heading', 'question', 'page_break', 'answer_space')) OR "
            "(node_kind = 'module' AND node_type = 'question_details') OR "
            "(node_kind = 'reference' AND node_type = 'answer_item')",
            name="kind_matches_type",
        ),
        # question 节点必须携带完整题目引用与冻结快照;其他节点不得携带。
        CheckConstraint(
            "(node_type = 'question' AND question_id IS NOT NULL AND "
            "question_revision IS NOT NULL AND content IS NOT NULL) OR "
            "(node_type <> 'question' AND question_id IS NULL AND "
            "question_revision IS NULL)",
            name="question_ref_matches_type",
        ),
        CheckConstraint(
            "(node_type = 'answer_item' AND source_question_node_id IS NOT NULL "
            "AND parent_id IS NOT NULL) OR "
            "(node_type <> 'answer_item' AND source_question_node_id IS NULL)",
            name="source_ref_matches_type",
        ),
        CheckConstraint(
            "anchor_before_node_id IS NULL OR "
            "(parent_id IS NOT NULL AND node_type IN ('heading', 'rich_text'))",
            name="anchor_matches_type",
        ),
        Index(
            "ix_composition_nodes_comp_parent_slot_pos",
            "composition_id", "parent_id", "slot", "position",
        ),
    )


class CompositionVersion(Base):
    """组稿的不可变版本快照。"""
    __tablename__ = "composition_versions"

    id = Column(Integer, primary_key=True, index=True)
    composition_id = Column(
        Integer, ForeignKey("compositions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no = Column(Integer, nullable=False)  # 每个 composition 内单调递增
    source_revision = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False)
    snapshot = Column(JSON, nullable=False)  # 不可变的完整快照
    label = Column(String(255), nullable=True)

    finalized_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finalized_by = Column(Integer, ForeignKey("user.id"), nullable=False)

    composition = relationship("Composition", back_populates="versions")
    subject = relationship("Subject")
    finalizer = relationship("User", foreign_keys=[finalized_by])

    __table_args__ = (
        UniqueConstraint("composition_id", "version_no", name="composition_version_no"),
    )


class CompositionEvent(Base):
    """组稿时间线事件,独立于 activity_logs(系统审计)。"""
    __tablename__ = "composition_events"

    id = Column(_BigIntPK, primary_key=True)
    composition_id = Column(
        Integer, ForeignKey("compositions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    composition_revision = Column(Integer, nullable=False)
    event_type = Column(String(50), nullable=False)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(64), nullable=True)
    summary = Column(String(255), nullable=False)
    payload = Column(JSON, nullable=True)
    batch_id = Column(String(64), nullable=True)

    actor_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    composition = relationship("Composition", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_id])

    __table_args__ = (
        Index("ix_composition_events_comp_id", "composition_id", "id"),
        Index("ix_composition_events_actor_created", "actor_id", "created_at"),
    )
