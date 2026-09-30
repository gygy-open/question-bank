import enum
from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint

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


class MediaOwnerType(str, enum.Enum):
    QUESTION = "question"
    STIMULUS = "stimulus"
    # 稿件工作区的全部节点合并为一个引用方;节点会被整批删建,按节点记不稳定。
    COMPOSITION = "composition"
    COMPOSITION_VERSION = "composition_version"


class MediaReference(Base):
    """资产被哪些内容引用;随内容写入同步维护,供"被引用于"与回收判断。"""

    __tablename__ = "media_references"
    __table_args__ = (
        UniqueConstraint("asset_id", "owner_type", "owner_id", name="uq_media_references_asset_owner"),
        Index("ix_media_references_owner", "owner_type", "owner_id"),
    )

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("media_assets.id"), nullable=False, index=True)
    owner_type = Column(String(32), nullable=False)
    owner_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class LegacyMediaPath(Base):
    """旧 /static/media URL → 内容寻址对象;迁移后旧目录可删,历史引用(含定稿快照)仍可解析。"""

    __tablename__ = "legacy_media_paths"

    id = Column(Integer, primary_key=True)
    # URL 解码后的完整路径,如 /static/media/images/a b.png。
    old_path = Column(String(512), nullable=False, unique=True)
    sha256 = Column(String(64), nullable=False, index=True)
    mime = Column(String(100), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
