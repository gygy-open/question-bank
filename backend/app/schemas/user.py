from pydantic import BaseModel
from datetime import datetime

class UserBase(BaseModel):
    username: str
    full_name: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    subject_id: int | None = None

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    username: str | None = None
    password: str | None = None
    full_name: str | None = None
    avatar_url: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    subject_id: int | None = None

class UserUpdatePassword(BaseModel):
    current_password: str
    new_password: str

class User(UserBase):
    id: int
    last_login: datetime | None = None
    login_count: int | None = 0

    class Config:
        from_attributes = True
