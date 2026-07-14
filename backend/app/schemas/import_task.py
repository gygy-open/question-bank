from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.import_task import ImportTaskStatus

class ImportTaskBase(BaseModel):
    description: Optional[str] = None
    source: Optional[str] = "manual"
    file_path: str
    original_filename: str
    file_type: str
    mode: Optional[str] = "extract"
    status: ImportTaskStatus = ImportTaskStatus.PENDING
    error_message: Optional[str] = None

class ImportTaskCreate(ImportTaskBase):
    user_id: Optional[int] = None

class ImportTaskUpdate(ImportTaskBase):
    pass

class ImportTask(ImportTaskBase):
    id: int
    user_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    result_summary: Optional[str] = None

    class Config:
        from_attributes = True
