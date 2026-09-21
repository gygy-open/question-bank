from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, UniqueConstraint

from .base import Base


class LegacyQuestionParentAudit(Base):
    __tablename__ = "legacy_question_parent_audits"
    __table_args__ = (
        UniqueConstraint("child_question_id", name="uq_legacy_question_parent_audits_child"),
    )

    id = Column(Integer, primary_key=True)
    child_question_id = Column(Integer, nullable=False)
    parent_question_id = Column(Integer, nullable=False)
    child_subject_id = Column(Integer, nullable=True)
    parent_subject_id = Column(Integer, nullable=True)
    child_deleted_at = Column(DateTime, nullable=True)
    parent_deleted_at = Column(DateTime, nullable=True)
    is_self_reference = Column(Boolean, nullable=False, default=False)
    is_parent_missing = Column(Boolean, nullable=False, default=False)
    is_cross_subject = Column(Boolean, nullable=False, default=False)
    has_soft_delete_mismatch = Column(Boolean, nullable=False, default=False)
    relation_id = Column(Integer, nullable=True)
    was_converted = Column(Boolean, nullable=False, default=False)
    archived_at = Column(DateTime, nullable=False, default=datetime.utcnow)
