from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Float, Index
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import Base


class PaperStatus(str, enum.Enum):
    DRAFT = "draft"
    ARCHIVED = "archived"


class Paper(Base):
    """试卷表: 一个用户可拥有多份试卷"""
    __tablename__ = 'papers'

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default=PaperStatus.DRAFT.value, nullable=False)

    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=True)
    owner_id = Column(Integer, ForeignKey('user.id'), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="papers")
    subject = relationship("Subject")
    items = relationship(
        "PaperQuestion",
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperQuestion.sequence",
    )


class PaperQuestion(Base):
    """试卷-题目关联表: 通过 sequence 维护题目顺序, 允许同题重复"""
    __tablename__ = 'paper_questions'

    id = Column(Integer, primary_key=True, index=True)
    paper_id = Column(Integer, ForeignKey('papers.id', ondelete='CASCADE'), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey('questions.id'), nullable=False)
    sequence = Column(Integer, nullable=False)  # 题目在试卷中的顺序 (0-based)
    section_title = Column(String(255), nullable=True)  # 预留: 分节标题 (V1.1)
    score = Column(Float, nullable=True)  # 预留: 题目分值

    paper = relationship("Paper", back_populates="items")
    question = relationship("Question")

    __table_args__ = (
        Index("ix_paper_seq", "paper_id", "sequence"),
    )
