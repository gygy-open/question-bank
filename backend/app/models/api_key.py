from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from .base import Base


class ApiKey(Base):
    """用户级 API Key,目前仅供 MCP 接入使用。权限完全继承所属用户。

    库里只存 SHA-256 哈希;明文只在创建时返回一次。撤销即删除行,审计留在 activity_log。
    """

    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    # 明文的前若干位,仅用于在界面上辨认是哪把 Key
    prefix = Column(String(16), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="api_keys")
