from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class Subject(Base):
    """科目表 (如: 数学, 英语)"""
    __tablename__ = 'subjects'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, index=True, nullable=False)
    slug = Column(String(255), unique=True, index=True, nullable=False) # 用于URL, 如 'math'
    description = Column(String(500), nullable=True)
    
    # 审核配置
    required_review_count = Column(Integer, default=1, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    updated_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    
    creator = relationship("User", foreign_keys=[created_by], back_populates="subjects_created")
    updater = relationship("User", foreign_keys=[updated_by], back_populates="subjects_updated")
    
    # 关系: 一个科目下有多个知识点
    knowledge_points = relationship("KnowledgePoint", back_populates="subject", cascade="all, delete-orphan")
