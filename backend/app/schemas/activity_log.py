from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from .user import User

class ActivityLogBase(BaseModel):
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    details: Optional[Union[Dict[str, Any], str]] = None
    ip_address: Optional[str] = None

class ActivityLogCreate(ActivityLogBase):
    user_id: Optional[int] = None

class ActivityLog(ActivityLogBase):
    id: int
    user_id: Optional[int] = None
    created_at: datetime
    user: Optional[User] = None

    class Config:
        from_attributes = True

class ActivityLogPage(BaseModel):
    items: List[ActivityLog]
    total: int
    page: int
    size: int
    pages: int
