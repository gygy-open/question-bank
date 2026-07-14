from pydantic import BaseModel
from typing import Optional

class TagCategoryBase(BaseModel):
    name: str
    slug: str
    sort_order: int = 0
    is_active: bool = True

class TagCategoryCreate(TagCategoryBase):
    pass

class TagCategoryUpdate(TagCategoryBase):
    name: Optional[str] = None
    slug: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class TagCategory(TagCategoryBase):
    id: int

    class Config:
        from_attributes = True
