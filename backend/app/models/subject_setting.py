from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.sql import func

from .base import Base


class SubjectSetting(Base):
    """学科级业务配置覆盖（JSON 值）。

    与 SubjectPrompt 同形：只有被显式定制的学科才有行，缺省时消费端回退到代码默认值，
    默认值不写入数据库。
    """

    __tablename__ = "subject_settings"
    __table_args__ = (
        UniqueConstraint("subject_id", "key", name="uq_subject_settings_subject_id_key"),
    )

    id = Column(Integer, primary_key=True, index=True)
    subject_id = Column(
        Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key = Column(String(50), nullable=False, index=True)
    value = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
