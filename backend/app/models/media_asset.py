import enum
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Integer, String

from .base import Base


class MediaPurpose(str, enum.Enum):
    CONTENT = "content"
    AVATAR = "avatar"
    CHAT = "chat"


class MediaKind(str, enum.Enum):
    IMAGE = "image"
    AUDIO = "audio"


class MediaStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class MediaAsset(Base):
    """媒体资产:指向不可变的内容寻址对象;来源、归属、用途都是元数据而非路径。"""

    __tablename__ = "media_assets"

    id = Column(Integer, primary_key=True, index=True)
    # purpose=content 时必填(按学科隔离);头像与对话附图归属用户,学科为空。
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)
    owner_user_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)
    purpose = Column(String(16), nullable=False)
    kind = Column(String(16), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    mime = Column(String(100), nullable=False)
    byte_size = Column(BigInteger, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration = Column(Float, nullable=True)
    original_filename = Column(String(255), nullable=True)
    alt = Column(String(500), nullable=True)
    source = Column(String(255), nullable=True)
    status = Column(String(16), nullable=False, default=MediaStatus.READY.value)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    deleted_at = Column(DateTime, nullable=True, index=True)
