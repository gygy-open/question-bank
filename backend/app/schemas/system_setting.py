from pydantic import BaseModel
from typing import Optional

class SystemSettingBase(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None

class SystemSettingCreate(SystemSettingBase):
    key: str

class SystemSettingUpdate(SystemSettingBase):
    pass

class SystemSetting(SystemSettingBase):
    key: str

    class Config:
        from_attributes = True
