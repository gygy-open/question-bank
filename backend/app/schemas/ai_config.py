from pydantic import BaseModel, field_validator
from typing import Optional, List

class AIModelBase(BaseModel):
    name: str
    is_vision_capable: bool = False
    is_embedding_model: bool = False

    @field_validator('is_vision_capable', 'is_embedding_model', mode='before')
    @classmethod
    def set_default_false(cls, v):
        return v if v is not None else False

class AIModelCreate(AIModelBase):
    pass

class AIModelUpdate(BaseModel):
    name: Optional[str] = None
    is_vision_capable: Optional[bool] = None
    is_embedding_model: Optional[bool] = None

class AIModel(AIModelBase):
    id: int
    provider_id: int

    class Config:
        from_attributes = True

class AIProviderBase(BaseModel):
    name: str
    interface_type: str
    base_url: Optional[str] = None
    is_active: bool = True

class AIProviderCreate(AIProviderBase):
    api_key: str
    models: List[AIModelCreate] = []

class AIProviderUpdate(BaseModel):
    name: Optional[str] = None
    interface_type: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None

class AIProvider(AIProviderBase):
    id: int
    models: List[AIModel] = []

    class Config:
        from_attributes = True
