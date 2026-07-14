from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SubjectBase(BaseModel):
    name: str
    slug: str
    description: Optional[str] = None
    required_review_count: int = 1

class SubjectCreate(SubjectBase):
    pass

class SubjectUpdate(SubjectBase):
    name: Optional[str] = None
    slug: Optional[str] = None
    required_review_count: Optional[int] = None

class Subject(SubjectBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
