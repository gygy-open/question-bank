from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.models.base import Base

class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255), index=True)
    avatar_url = Column(String(255))
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean(), default=True)
    is_superuser = Column(Boolean(), default=False)
    
    # Login stats
    last_login = Column(DateTime, nullable=True)
    login_count = Column(Integer, default=0)
    
    # 用户负责的科目
    subject_id = Column(Integer, ForeignKey("subjects.id"), nullable=True, index=True)

    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="user")

    # ImportTask
    import_tasks = relationship("ImportTask", back_populates="user")
    
    # Question
    questions_created = relationship("Question", foreign_keys="Question.created_by", back_populates="creator")

    prompt_templates = relationship("PromptTemplate", back_populates="user", cascade="all, delete-orphan")
    questions_updated = relationship("Question", foreign_keys="Question.updated_by", back_populates="updater")
    
    # Subject
    subjects_created = relationship("Subject", foreign_keys="Subject.created_by", back_populates="creator")
    subjects_updated = relationship("Subject", foreign_keys="Subject.updated_by", back_populates="updater")
    
    # KnowledgePoint
    knowledge_points_created = relationship("KnowledgePoint", foreign_keys="KnowledgePoint.created_by", back_populates="creator")
    knowledge_points_updated = relationship("KnowledgePoint", foreign_keys="KnowledgePoint.updated_by", back_populates="updater")
    
    # Tag
    tags_created = relationship("Tag", foreign_keys="Tag.created_by", back_populates="creator")
    tags_updated = relationship("Tag", foreign_keys="Tag.updated_by", back_populates="updater")
