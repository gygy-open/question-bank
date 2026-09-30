from pydantic import BaseModel, Field, computed_field
from typing import Optional
from datetime import datetime
from app.core.file_paths import import_source_file
from app.models.import_task import ImportTaskStatus

class ImportTaskBase(BaseModel):
    description: Optional[str] = None
    source: Optional[str] = "manual"
    original_filename: str
    file_type: str
    mode: Optional[str] = "extract"
    status: ImportTaskStatus = ImportTaskStatus.PENDING
    error_message: Optional[str] = None

class ImportTaskCreate(ImportTaskBase):
    file_path: str
    user_id: Optional[int] = None

class ImportTaskUpdate(ImportTaskBase):
    pass

class ImportTask(ImportTaskBase):
    id: int
    user_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    # 服务器路径不外露;只告诉前端能否"查看源文件"。
    file_path: Optional[str] = Field(default=None, exclude=True)

    @computed_field
    @property
    def has_source(self) -> bool:
        return import_source_file(self.file_path) is not None

    class Config:
        from_attributes = True
