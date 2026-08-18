from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON,
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import Base


class CompositionStatus(str, enum.Enum):
    DRAFT = "draft"           # 草稿
    PUBLISHED = "published"   # 发布/公开
    ARCHIVED = "archived"     # 归档


class FolderScope(str, enum.Enum):
    """空间隔离: 团队共享 or 仅本人可见."""
    TEAM = "team"
    PERSONAL = "personal"


class BlockType(str, enum.Enum):
    HEADING = "heading"              # 大题/分节标题
    TEXT = "text"                    # 富文本段落 (markdown)
    QUESTION = "question"            # 引用单题
    COMPONENT_REF = "component_ref"  # 引用整个题组(跟随更新, 可拆开)
    PAGE_BREAK = "page_break"        # 分页符


class Folder(Base):
    """树形文件夹. 任何组稿都在某级文件夹下."""
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL = 树根
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    scope = Column(String(20), nullable=False, default=FolderScope.PERSONAL.value, index=True)
    sequence = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    children = relationship("Folder", backref="parent", remote_side=[id])

    __table_args__ = (
        Index("ix_folders_tree", "subject_id", "scope"),
    )


class Composition(Base):
    """通用组稿: 题组/讲义/试卷等各类图文混合文档."""
    __tablename__ = "compositions"

    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True)

    comp_type = Column(String(50), nullable=False, index=True)  # 决定文档表现形式: question_group / exam_paper / study_guide / handout ...
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=CompositionStatus.DRAFT.value, nullable=False, index=True)

    difficulty = Column(Integer, nullable=True)                 
    meta_data = Column(JSON, nullable=True)                     

    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="compositions", primaryjoin="Composition.owner_id == User.id")
    folder = relationship("Folder")
    blocks = relationship(
        "CompositionBlock",
        back_populates="composition",
        cascade="all, delete-orphan",
        order_by="CompositionBlock.sequence",
        foreign_keys="CompositionBlock.composition_id",
    )

    @property
    def subject_id(self):
        return self.folder.subject_id if self.folder else None

    @property
    def scope(self):
        return self.folder.scope if self.folder else None


class CompositionBlock(Base):
    """内容块: 题组与作品共用. component_ref 走同表自引用实现引用式编排."""
    __tablename__ = "composition_blocks"

    id = Column(Integer, primary_key=True, index=True)
    composition_id = Column(
        Integer, ForeignKey("compositions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    block_type = Column(String(50), nullable=False)
    sequence = Column(Integer, nullable=False)  # 块在文档中的顺序 (0-based)
    # 块专属数据: text -> {"text": md}; heading -> {"text": str, "level": int}; question -> {"score": float}
    content = Column(JSON, nullable=True)

    # 引用(按 block_type 二选一)
    ref_question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)        # question
    ref_composition_id = Column(Integer, ForeignKey("compositions.id"), nullable=True)  # component_ref -> 指向题组

    composition = relationship("Composition", back_populates="blocks", foreign_keys=[composition_id])
    question = relationship("Question")
    ref_composition = relationship("Composition", foreign_keys=[ref_composition_id])

    __table_args__ = (
        Index("ix_comp_block_seq", "composition_id", "sequence"),
    )
