from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import relationship

from .base import Base
from .question import QuestionStatus, QuestionVisibility


_RichTextColumn = LONGTEXT().with_variant(Text(), "sqlite")


class Stimulus(Base):
    """题目材料：不可作答、可被若干小题（Question.stimulus_id）共享的上下文。"""

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
    # 乐观锁版本：任何写入（含状态、小题成员与顺序）都递增。
    revision = Column(Integer, nullable=False, default=1)
    # 内容版本：仅正文变化时递增，供组稿判断材料快照是否过期。
    content_revision = Column(Integer, nullable=False, default=1, server_default="1")
    deleted_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    created_by = Column(Integer, ForeignKey("user.id"), nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id"), nullable=True)

    subject = relationship("Subject")
    questions = relationship(
        "Question",
        back_populates="stimulus",
        order_by="Question.stimulus_position",
    )
