from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Index, JSON, Table,
)
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import Base


class PublicationStatus(str, enum.Enum):
    DRAFT = "draft"
    ARCHIVED = "archived"


class PublicationType(str, enum.Enum):
    """出版物类型: 试卷 / 学案 / 题组 ..."""
    EXAM_PAPER = "exam_paper"
    STUDY_GUIDE = "study_guide"
    QUESTION_GROUP = "question_group"


class BlockType(str, enum.Enum):
    """内容块类型"""
    HEADING = "heading"        # 大题/分节标题
    TEXT = "text"              # 富文本段落 (markdown)
    QUESTION = "question"      # 引用题库中的题目
    PAGE_BREAK = "page_break"  # 分页符


# 出版物与知识点的多对多 (供题组等按知识点树检索)
publication_knowledge_points = Table(
    'publication_knowledge_points',
    Base.metadata,
    Column('publication_id', Integer, ForeignKey('publications.id', ondelete='CASCADE'), primary_key=True),
    Column('knowledge_point_id', Integer, ForeignKey('knowledge_points.id'), primary_key=True),
)


class Publication(Base):
    """通用出版物: 由有序内容块 (Block) 组成的可发布文档 (试卷/学案/题组)"""
    __tablename__ = 'publications'

    id = Column(Integer, primary_key=True, index=True)
    pub_type = Column(String(50), default=PublicationType.EXAM_PAPER.value, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=PublicationStatus.DRAFT.value, nullable=False)
    difficulty = Column(Integer, nullable=True)  # 题组难度评估等元数据
    meta_data = Column(JSON, nullable=True)       # 场景专属扩展配置

    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=True)
    owner_id = Column(Integer, ForeignKey('user.id'), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="publications")
    subject = relationship("Subject")
    knowledge_points = relationship("KnowledgePoint", secondary=publication_knowledge_points)
    blocks = relationship(
        "PublicationBlock",
        back_populates="publication",
        cascade="all, delete-orphan",
        order_by="PublicationBlock.sequence",
    )


class PublicationBlock(Base):
    """出版物内容块: 通过 sequence 维护顺序, 承载文本/标题/题目引用/分页等"""
    __tablename__ = 'publication_blocks'

    id = Column(Integer, primary_key=True, index=True)
    publication_id = Column(
        Integer, ForeignKey('publications.id', ondelete='CASCADE'), nullable=False, index=True
    )
    block_type = Column(String(50), nullable=False)
    sequence = Column(Integer, nullable=False)  # 块在文档中的顺序 (0-based)
    # 块专属数据: text -> {"text": md}; heading -> {"text": str, "level": int}; question -> {"score": float}
    content = Column(JSON, nullable=True)
    ref_question_id = Column(Integer, ForeignKey('questions.id'), nullable=True)

    publication = relationship("Publication", back_populates="blocks")
    question = relationship("Question")

    __table_args__ = (
        Index("ix_pub_block_seq", "publication_id", "sequence"),
    )
