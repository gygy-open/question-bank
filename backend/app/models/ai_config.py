from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class AIProvider(Base):
    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True, index=True)
    # 同一归属(全局 / 某个用户)内唯一,由应用层校验;MySQL 唯一索引放行多个 NULL,无法覆盖全局场景。
    name = Column(String(100), index=True, nullable=False)  # e.g. "Official OpenAI", "DeepSeek"
    interface_type = Column(String(20), nullable=False)  # "openai" or "gemini"
    base_url = Column(String(255), nullable=True)
    api_key = Column(String(512), nullable=False)  # 加密存储,见 app.core.secrets
    is_active = Column(Boolean, default=True)
    # NULL = 全局(管理员维护,所有人可用);非 NULL = 该用户的个人服务商
    owner_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)

    models = relationship("AIModel", back_populates="provider", cascade="all, delete-orphan")
    owner = relationship("User", back_populates="ai_providers")

    @property
    def is_personal(self) -> bool:
        return self.owner_id is not None

    @property
    def api_key_set(self) -> bool:
        return bool(self.api_key)

    @property
    def owner_name(self) -> str | None:
        owner = self.__dict__.get("owner")
        if owner is None:
            return None
        return owner.full_name or owner.username

class AIModel(Base):
    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=False)
    name = Column(String(100), nullable=False)  # The actual model string, e.g. "gpt-4o"
    is_vision_capable = Column(Boolean, default=False)
    is_embedding_model = Column(Boolean, default=False)
    
    provider = relationship("AIProvider", back_populates="models")


class UserAIPreference(Base):
    """用户个人默认模型;为空表示沿用全局激活模型。向量模型始终走全局,不在此处。"""

    __tablename__ = "user_ai_preferences"

    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True)
    text_model_id = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
    vision_model_id = Column(Integer, ForeignKey("ai_models.id", ondelete="SET NULL"), nullable=True)
