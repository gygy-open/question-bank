from typing import List
from pydantic import BaseModel, Field
from datetime import datetime

class UserBase(BaseModel):
    username: str
    full_name: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    subject_id: int | None = None
    last_active_subject_id: int | None = None

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
    last_active_subject_id: int | None = None

class UserUpdateLastSubject(BaseModel):
    subject_id: int

class UserUpdatePassword(BaseModel):
    current_password: str
    new_password: str

class User(UserBase):
    id: int
    last_login: datetime | None = None
    login_count: int | None = 0

    class Config:
        from_attributes = True

class RegisterRequest(BaseModel):
    username: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    password: str = Field(min_length=6)

class RegisterResult(BaseModel):
    ok: bool
    requires_approval: bool

class RegistrationConfig(BaseModel):
    enabled: bool
    requires_approval: bool

class UserImportRowError(BaseModel):
    row: int
    message: str

class UserImportResult(BaseModel):
    status: str  # success | partial | failed
    created: int = 0
    failed: int = 0
    total: int = 0
    errors: List[UserImportRowError] = []
