import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .base import Base


class QuestionRelationType(str, enum.Enum):
    DECOMPOSED_FROM = "decomposed_from"


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
        Index(
            "ix_question_relations_target_question_id_relation_type",
            "target_question_id",
            "relation_type",
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
