from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SQLEnum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from .base import Base

class ImportTaskStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ImportTask(Base):
    __tablename__ = 'import_tasks'
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('user.id'), nullable=True)
    description = Column(String(255), nullable=True)
    source = Column(String(50), default="manual")
    
    file_path = Column(String(512), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False) # docx, markdown
    mode = Column(String(20), default="extract") # extract, solve
    
    status = Column(SQLEnum(ImportTaskStatus, values_callable=lambda x: [e.value for e in x]), default=ImportTaskStatus.PENDING, index=True)
    error_message = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True) # JSON string of results
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="import_tasks")
    questions = relationship("Question", back_populates="import_task")
