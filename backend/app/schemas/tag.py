from pydantic import BaseModel
from typing import List, Optional

class TagBase(BaseModel):
    name: str
    category_id: Optional[int] = None # NULL = 未分类
    color: Optional[str] = "#grey"

class TagCreate(TagBase):
    subject_id: int

class TagUpdate(TagBase):
    name: Optional[str] = None
    category_id: Optional[int] = None

class Tag(TagBase):
    id: int
    subject_id: int

    class Config:
        from_attributes = True


class TagPage(BaseModel):
    items: List[Tag]
    total: int
    page: int
    size: int
    pages: int


class TagImportRowError(BaseModel):
    row: int
    message: str


class TagImportResult(BaseModel):
    status: str  # "success" | "failed"
    created: int
    failed: int
    skipped: int  # duplicate names skipped (not treated as errors)
    total: int
    errors: List[TagImportRowError]
