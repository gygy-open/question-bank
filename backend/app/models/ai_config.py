from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from .base import Base

class AIProvider(Base):
    __tablename__ = "ai_providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True, nullable=False)  # e.g. "Official OpenAI", "DeepSeek"
    interface_type = Column(String(20), nullable=False)  # "openai" or "gemini"
    base_url = Column(String(255), nullable=True)
    api_key = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    
    models = relationship("AIModel", back_populates="provider", cascade="all, delete-orphan")

class AIModel(Base):
    __tablename__ = "ai_models"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, ForeignKey("ai_providers.id"), nullable=False)
    name = Column(String(100), nullable=False)  # The actual model string, e.g. "gpt-4o"
    is_vision_capable = Column(Boolean, default=False)
    is_embedding_model = Column(Boolean, default=False)
    
    provider = relationship("AIProvider", back_populates="models")
