from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    created_at: datetime
    last_used_at: Optional[datetime] = None


class ApiKeyCreated(ApiKeyRead):
    # 明文只在创建响应里出现这一次
    key: str


class ApiKeyAdminRead(ApiKeyRead):
    user_id: int
    username: str
    full_name: Optional[str] = None


class McpInfo(BaseModel):
    enabled: bool
    # 相对路径,前端拼上 window.location.origin 得到接入地址;局域网地址复用 /system/network
    path: str


class McpSettingsUpdate(BaseModel):
    enabled: bool
