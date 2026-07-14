from pydantic import BaseModel
from typing import Optional

class TagBase(BaseModel):
    name: str
    category: str = "general" # 默认分类
    color: Optional[str] = "#grey"

class TagCreate(TagBase):
    pass

class TagUpdate(TagBase):
    name: Optional[str] = None
    category: Optional[str] = None

class Tag(TagBase):
    id: int

    class Config:
        from_attributes = True
