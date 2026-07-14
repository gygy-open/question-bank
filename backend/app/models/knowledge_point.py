from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship, backref
from .base import Base

class KnowledgePoint(Base):
    """知识点表 (支持树形结构, 如: 数学 -> 高数 -> 微积分)"""
    __tablename__ = 'knowledge_points'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True, nullable=False)
    slug = Column(String(255), index=True, nullable=False)
    
    subject_id = Column(Integer, ForeignKey('subjects.id'), nullable=False)
    parent_id = Column(Integer, ForeignKey('knowledge_points.id', ondelete='CASCADE'), nullable=True) # 父知识点ID
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    created_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    updated_by = Column(Integer, ForeignKey('user.id'), nullable=True)
    
    creator = relationship("User", foreign_keys=[created_by], back_populates="knowledge_points_created")
    updater = relationship("User", foreign_keys=[updated_by], back_populates="knowledge_points_updated")

    # 关系
    subject = relationship("Subject", back_populates="knowledge_points")
    # 自关联: 获取子知识点
    children = relationship(
        "KnowledgePoint", 
        backref=backref('parent', remote_side=[id]),
        cascade="all, delete-orphan"
    )
    questions = relationship("Question", secondary="question_knowledge_points", back_populates="knowledge_points")

    __table_args__ = (
        UniqueConstraint('subject_id', 'slug', name='uq_knowledge_point_subject_slug'),
    )
