from pydantic import BaseModel, ConfigDict, field_validator
from typing import Literal, Optional, List

InterfaceType = Literal["openai", "gemini"]


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

    model_config = ConfigDict(from_attributes=True)

class AIProviderBase(BaseModel):
    name: str
    interface_type: InterfaceType
    base_url: Optional[str] = None
    is_active: bool = True

class AIProviderCreate(AIProviderBase):
    api_key: str
    models: List[AIModelCreate] = []

class AIProviderUpdate(BaseModel):
    name: Optional[str] = None
    interface_type: Optional[InterfaceType] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    is_active: Optional[bool] = None

class AIProvider(AIProviderBase):
    """响应体从不包含 API Key,只告知是否已设置。"""

    id: int
    interface_type: str  # 兼容历史数据,响应不做枚举校验
    owner_id: Optional[int] = None
    owner_name: Optional[str] = None
    is_personal: bool = False
    api_key_set: bool = False
    models: List[AIModel] = []

    model_config = ConfigDict(from_attributes=True)


class DiscoverModelsRequest(BaseModel):
    """新建时传完整凭据;编辑已有服务商时可只传 provider_id,后端用已保存的 Key。"""

    interface_type: Optional[InterfaceType] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    provider_id: Optional[int] = None


class DiscoveredModel(AIModelBase):
    pass


class DiscoverModelsResponse(BaseModel):
    ok: bool
    message: str
    models: List[DiscoveredModel] = []


class UserAIPreferenceUpdate(BaseModel):
    text_model_id: Optional[int] = None
    vision_model_id: Optional[int] = None


class EffectiveModel(BaseModel):
    model_id: Optional[int] = None
    source: Optional[Literal["personal", "global"]] = None
    error: Optional[str] = None


class UserAIPreference(UserAIPreferenceUpdate):
    """个人默认 + 实际生效的模型(个人默认不可用时回落到全局)。"""

    effective_text: EffectiveModel = EffectiveModel()
    effective_vision: EffectiveModel = EffectiveModel()
