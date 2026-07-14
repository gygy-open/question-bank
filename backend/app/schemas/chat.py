from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

# Message Schemas
class ChatMessageBase(BaseModel):
    role: str
    content: Optional[str] = None
    images: Optional[List[str]] = None # List of file paths
    tool_calls: Optional[List[Dict[str, Any]]] = None

class ChatMessageCreate(ChatMessageBase):
    pass

class ChatMessageUpdate(BaseModel):
    content: Optional[str] = None
    images: Optional[List[str]] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None

class ChatMessage(ChatMessageBase):
    id: int
    session_id: str
    created_at: datetime

    class Config:
        from_attributes = True

# Session Schemas
class ChatSessionBase(BaseModel):
    title: Optional[str] = None

class ChatSessionCreate(ChatSessionBase):
    pass

class ChatSessionUpdate(ChatSessionBase):
    pass

class ChatSessionSummary(ChatSessionBase):
    id: str
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ChatSession(ChatSessionSummary):
    messages: List[ChatMessage] = []

    class Config:
        from_attributes = True

# Request Schemas (for API)
class ChatRequest(BaseModel):
    model_id: int
    message: ChatMessageCreate # The new message to add
    stream: bool = True
    temperature: Optional[float] = 0.7
