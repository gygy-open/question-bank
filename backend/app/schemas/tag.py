from pydantic import BaseModel
from typing import Optional

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
