from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from .base import Base


class SubjectMember(Base):
    """用户-学科成员关系:承载学科作用域角色。

    role 存字符串(应用层校验取值 viewer/editor/manager),不用 DB 原生 ENUM,
    以便将来追加新角色时零迁移(前向兼容约束)。
    """
    __tablename__ = "subject_members"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subject_id = Column(
        Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String(20), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="subject_memberships")
    subject = relationship("Subject")

    __table_args__ = (
        UniqueConstraint("user_id", "subject_id", name="user_subject"),
    )
