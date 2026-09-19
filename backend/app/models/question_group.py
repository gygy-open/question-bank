import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from .base import Base
from .question import QuestionStatus, QuestionVisibility


_RichTextColumn = LONGTEXT().with_variant(Text(), "sqlite")


class QuestionRelationType(str, enum.Enum):
    DECOMPOSED_FROM = "decomposed_from"


class Stimulus(Base):
    __tablename__ = "stimuli"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    content = Column(_RichTextColumn, nullable=False)
    status = Column(String(20), nullable=False, default=QuestionStatus.DRAFT.value)
    visibility = Column(
        String(20), nullable=False, default=QuestionVisibility.PUBLIC.value
    )
    source = Column(String(255), nullable=True)
    metadata_json = Column("metadata", _RichTextColumn, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    deleted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    subject = relationship("Subject")
    groups = relationship("QuestionGroup", back_populates="stimulus")


class QuestionGroup(Base):
    __tablename__ = "question_groups"

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=False, index=True)
    stimulus_id = Column(Integer, ForeignKey("stimuli.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=QuestionStatus.DRAFT.value)
    visibility = Column(
        String(20), nullable=False, default=QuestionVisibility.PUBLIC.value
    )
    source = Column(String(255), nullable=True)
    metadata_json = Column("metadata", _RichTextColumn, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    deleted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    subject = relationship("Subject")
    stimulus = relationship("Stimulus", back_populates="groups")
    items = relationship(
        "QuestionGroupItem",
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="QuestionGroupItem.position",
    )


class QuestionGroupItem(Base):
    __tablename__ = "question_group_items"
    __table_args__ = (
        UniqueConstraint(
            "group_id", "question_id", name="uq_question_group_items_question"
        ),
        UniqueConstraint(
            "group_id", "position", name="uq_question_group_items_position"
        ),
        CheckConstraint("position >= 0", name="position_non_negative"),
    )

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer, ForeignKey("question_groups.id", ondelete="CASCADE"), nullable=False
    )
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    position = Column(Integer, nullable=False)

    group = relationship("QuestionGroup", back_populates="items")
    question = relationship("Question")


class QuestionRelation(Base):
    """有向关系：target_question_id decomposed_from source_question_id。"""

    __tablename__ = "question_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_question_id",
            "target_question_id",
            "relation_type",
            name="uq_question_relations_edge",
        ),
        CheckConstraint(
            "source_question_id <> target_question_id", name="different_questions"
        ),
    )

    id = Column(Integer, primary_key=True)
    source_question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    target_question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    relation_type = Column(
        String(32), nullable=False, default=QuestionRelationType.DECOMPOSED_FROM.value
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    source_question = relationship("Question", foreign_keys=[source_question_id])
    target_question = relationship("Question", foreign_keys=[target_question_id])