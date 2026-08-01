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


# --- Vector sync (deferred indexing) ---

class VectorStatus(BaseModel):
    embedding_configured: bool
    db_count: int
    vector_count: int
    needs_reindex: bool
    reason: str


class ReindexResult(BaseModel):
    status: str
    reindexed: int
    duration: float


# --- Batch import ---

class KPImportRowError(BaseModel):
    row: int
    message: str


class KPImportResult(BaseModel):
    status: str  # success | partial | failed
    subject_name: Optional[str] = None
    mode: str
    created: int = 0
    skipped: int = 0
    failed: int = 0
    total: int = 0
    duration: float = 0.0
    vector_synced: bool = False
    errors: List[KPImportRowError] = []


class KPImportPreflight(BaseModel):
    subject_id: int
    subject_name: str
    existing_count: int
    affected_questions: int
