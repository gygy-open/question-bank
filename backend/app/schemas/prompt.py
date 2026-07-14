from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class PromptTemplateBase(BaseModel):
    title: str
    content: str

class PromptTemplateCreate(PromptTemplateBase):
    pass

class PromptTemplateUpdate(PromptTemplateBase):
    title: Optional[str] = None
    content: Optional[str] = None

class PromptTemplate(PromptTemplateBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
