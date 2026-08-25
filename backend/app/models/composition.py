"""组稿 (Composition) 领域模型 —— 第一阶段 schema。

设计要点(与已确认 ADR 对齐):
- 不建 spaces/space_members 表。Folder / Composition 直接持久化 scope_type + owner_id:
  shared → owner_id 为 NULL;personal → owner_id 非 NULL(由 CheckConstraint 保证)。
- Subject 是强上下文:folders / compositions 的 subject_id 均 NOT NULL。
- CompositionBlock 首期为线性序列(不含 parent_id),type 枚举仅 5 种;富文本自由内容由
  rich_text 承担。question_id / question_revision 仅 question block 使用。
- composition_versions 存不可变 snapshot JSON;composition_events 独立于 activity_logs。
- Block ID 采用 BigInteger:与仓库既有的自增整型 PK 习惯一致,又为大量 block 预留空间;
  相比 UUID 免去 MySQL CHAR(36)/BINARY(16) 存储与客户端生成的复杂度(权衡见 ADR)。
"""
from datetime import datetime
import enum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import Base

# BigInteger 供 MySQL 大容量自增 PK;SQLite 仅对 INTEGER PRIMARY KEY 做 rowid 自增,
# 故在 SQLite(桌面版/测试)上退化为 INTEGER 以保留自增语义。
_BlockPK = BigInteger().with_variant(Integer(), "sqlite")


class ScopeType(str, enum.Enum):
    """归属范围:共享(团队可见)或个人私有。"""
    SHARED = "shared"
    PERSONAL = "personal"


class CompositionStatus(str, enum.Enum):
    DRAFT = "draft"
    ARCHIVED = "archived"


class CompositionBlockType(str, enum.Enum):
    RICH_TEXT = "rich_text"
    HEADING = "heading"
    QUESTION = "question"
    PAGE_BREAK = "page_break"
    ANSWER_SUMMARY = "answer_summary"


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
        # 行级 CheckConstraint 表达。此处不伪造数据库保证,改由服务层(下一阶段)强制。
    )


class Composition(Base):
    """组稿:一份可编辑的稿件,由有序 block 组成,可产生不可变版本快照。"""
    __tablename__ = "compositions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=CompositionStatus.DRAFT.value, nullable=False)
    revision = Column(Integer, default=1, nullable=False)

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

    blocks = relationship(
        "CompositionBlock",
        back_populates="composition",
        cascade="all, delete-orphan",
        order_by="CompositionBlock.sequence",
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


class CompositionBlock(Base):
    """组稿内的有序块。首期线性序列,无 parent_id。"""
    __tablename__ = "composition_blocks"

    id = Column(_BlockPK, primary_key=True)
    composition_id = Column(
        Integer, ForeignKey("compositions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence = Column(Integer, nullable=False)  # 线性顺序 (0-based)
    block_type = Column(_enum_col(CompositionBlockType), nullable=False)

    # 结构化内容:rich_text 存 RichDoc,heading 存标题内容,page_break/question 为 NULL。
    content = Column(JSON, nullable=True)
    props = Column(JSON, nullable=True)
    schema_version = Column(Integer, default=1, nullable=False)

    # 仅 question block 使用:引用题目及被钉住的修订号。
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=True, index=True)
    question_revision = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    composition = relationship("Composition", back_populates="blocks")
    question = relationship("Question")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    __table_args__ = (
        # question block 必须携带完整引用,其他 block 不得携带。
        CheckConstraint(
            "(block_type = 'question' AND question_id IS NOT NULL AND "
            "question_revision IS NOT NULL) OR "
            "(block_type <> 'question' AND question_id IS NULL AND "
            "question_revision IS NULL)",
            name="question_ref_matches_type",
        ),
        Index("ix_composition_blocks_comp_seq", "composition_id", "sequence"),
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

    id = Column(_BlockPK, primary_key=True)
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
