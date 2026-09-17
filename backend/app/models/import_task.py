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


class CompositionImportState(str, enum.Enum):
    """稿件生成子状态。与 ImportTaskStatus 正交:题目入库成功即 COMPLETED,
    稿件是否生成单独表达,避免引入"部分完成"这类复合任务状态。"""

    NOT_REQUESTED = "not_requested"
    CREATED = "created"
    FAILED = "failed"


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

    # 上传文件内容的 SHA-256;仅用于"完全一致"的重复上传提示,不做近似查重。
    content_sha256 = Column(String(64), nullable=True, index=True)
    # 整卷导入提交的幂等键;重放同一请求返回既有结果而非重复建题/建稿。
    idempotency_key = Column(String(64), nullable=True, unique=True)
    composition_state = Column(
        SQLEnum(CompositionImportState, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CompositionImportState.NOT_REQUESTED,
        server_default=CompositionImportState.NOT_REQUESTED.value,
    )
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    user = relationship("User", back_populates="import_tasks")
    questions = relationship("Question", back_populates="import_task")
    # 反向导航:稿件侧持有 FK,此处按 source_import_task_id 关联(无循环外键)。
    compositions = relationship(
        "Composition",
        back_populates="source_import_task",
        foreign_keys="Composition.source_import_task_id",
    )
