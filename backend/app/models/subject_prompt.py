from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


class SubjectPrompt(Base):
    """科目级提示词覆盖。

    只有被用户显式定制的科目才有行；缺省时消费端回退到代码默认值
    (app/services/prompts.py 的 SUBJECT_PROMPTS)，默认值不写入数据库。
    """

    __tablename__ = "subject_prompts"
    __table_args__ = (
        UniqueConstraint("subject_id", "key", name="uq_subject_prompts_subject_id_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key = Column(String(50), nullable=False, index=True)
    value = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
