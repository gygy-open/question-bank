from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON,
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import Base


class CompositionKind(str, enum.Enum):
    """组稿的性质; folder 按它分成两棵树(资源库/作品库)."""
    COMPONENT = "component"      # 题组等可复用预制件
    DELIVERABLE = "deliverable"  # 试卷 / 学案 / 讲义等交付物


class CompositionStatus(str, enum.Enum):
    DRAFT = "draft"           # 题组=未公开草稿; 作品=编辑中
    PUBLISHED = "published"   # 题组进入共享库
    ARCHIVED = "archived"


class CompositionScope(str, enum.Enum):
    """仅 deliverable 树有意义."""
    TEAM = "team"             # 教研组共享, 全员可编辑
    PERSONAL = "personal"     # 仅本人


class BlockType(str, enum.Enum):
    HEADING = "heading"              # 大题/分节标题
    TEXT = "text"                    # 富文本段落 (markdown)
    QUESTION = "question"            # 引用单题
    COMPONENT_REF = "component_ref"  # 引用整个题组(跟随更新, 可拆开)
    PAGE_BREAK = "page_break"        # 分页符


class Folder(Base):
    """树形文件夹, 是 subject/scope/kind 的唯一权威; 组稿归属其一并继承这些属性.

    约束(应用层保证): 子文件夹的 subject_id/kind/scope 必须与父一致.
    """
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=True, index=True)  # NULL = 树根
    kind = Column(String(20), nullable=False)                                    # component / deliverable
    scope = Column(String(20), nullable=True)                                    # 仅 deliverable 树: team / personal
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)  # 建者; personal 树据此区分各用户
    sequence = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    children = relationship("Folder", backref="parent", remote_side=[id])

    __table_args__ = (
        Index("ix_folders_tree", "subject_id", "kind", "scope"),
    )


class Composition(Base):
    """通用组稿: 题组(component) 与 作品(deliverable) 统一, 由有序块编排组合.

    subject_id / scope / kind 均不落库 —— 由所属 folder(kind 亦可由 comp_type 注册表映射)派生.
    """
    __tablename__ = "compositions"

    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("folders.id", ondelete="CASCADE"), nullable=False, index=True)

    comp_type = Column(String(50), nullable=False, index=True)  # 注册表驱动: question_group / exam_paper / study_guide / handout ...
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=CompositionStatus.DRAFT.value, nullable=False, index=True)

    difficulty = Column(Integer, nullable=True)                 # 题组元数据(非派生, 保留)
    meta_data = Column(JSON, nullable=True)                     # 各 comp_type 扩展: 分值 / 导出偏好 / 蓝图

    owner_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)  # 创建人(≠ folder.owner_id)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="compositions")
    folder = relationship("Folder")
    blocks = relationship(
        "CompositionBlock",
        back_populates="composition",
        cascade="all, delete-orphan",
        order_by="CompositionBlock.sequence",
        foreign_keys="CompositionBlock.composition_id",
    )

    # 便捷派生(读取需 folder 已加载; 查询时按 folder join 过滤)
    @property
    def subject_id(self):
        return self.folder.subject_id if self.folder else None

    @property
    def scope(self):
        return self.folder.scope if self.folder else None

    @property
    def kind(self):
        return self.folder.kind if self.folder else None


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
