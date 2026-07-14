from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class KnowledgePointBase(BaseModel):
    name: str
    slug: str
    parent_id: Optional[int] = None

class KnowledgePointCreate(KnowledgePointBase):
    subject_id: int

class KnowledgePointUpdate(KnowledgePointBase):
    name: Optional[str] = None
    slug: Optional[str] = None
    subject_id: Optional[int] = None

class KnowledgePoint(KnowledgePointBase):
    id: int
    subject_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
