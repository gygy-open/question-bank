from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class ActivityLog(Base):
    """用户行为记录表"""
    __tablename__ = 'activity_logs'

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
    action = Column(String(50), nullable=False) # create, update, delete, login, etc.
    resource_type = Column(String(50), nullable=True) # question, knowledge_point, subject, tag, user
    resource_id = Column(Integer, nullable=True)
    details = Column(JSON, nullable=True) # 变更详情, 快照等
    ip_address = Column(String(50), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="activity_logs")
