"""AI 服务商 / 模型配置。

- 全局(管理员):/providers、/models、/active-config。服务商 owner_id 为空,所有人可用。
- 个人(任意登录用户):/me/providers、/me/models、/me/preferences。只有本人可用,Key 不对任何人回显。
- 工具:/discover-models 测试连接并拉取模型列表。
"""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.capabilities.errors import Forbidden, Invalid
from app.core.api_errors import ErrorCode
from app.crud.crud_system_setting import system_setting
from app.models.user import User
from app.schemas.ai_config import (
    AIModel as AIModelSchema,
    AIModelCreate,
    AIModelUpdate,
    AIProvider as AIProviderSchema,
    AIProviderCreate,
    AIProviderUpdate,
    DiscoverModelsRequest,
    DiscoverModelsResponse,
    EffectiveModel,
    UserAIPreference as UserAIPreferenceSchema,
    UserAIPreferenceUpdate,
)
from app.services import ai_config_service as svc
from app.services.ai_config_service import EMBEDDING_MODEL_KEY, validate_active_model
from app.services.ai_resolver import resolve_model

router = APIRouter()


async def _reload_embedding() -> None:
    from app.services.embedding import reload_embedding_function

    await reload_embedding_function()


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------

@router.get("/providers", response_model=List[AIProviderSchema])
async def read_ai_providers(
    db: AsyncSession = Depends(deps.get_db),
    include_personal: bool = False,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """全局 + 自己的服务商。管理员带 include_personal=true 时返回所有人的(用于审查,不含 Key)。"""
    if include_personal and not current_user.is_superuser:
        raise Forbidden("Not enough privileges", ErrorCode.AUTH_FORBIDDEN)
    return await svc.list_providers(db, user_id=current_user.id, include_all=include_personal)


# ---------------------------------------------------------------------------
# 全局服务商(管理员)
# ---------------------------------------------------------------------------

@router.post("/providers", response_model=AIProviderSchema)
async def create_ai_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_in: AIProviderCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    return await svc.create_provider(db, obj_in=provider_in, owner_id=None)


@router.put("/providers/{provider_id}", response_model=AIProviderSchema)
async def update_ai_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    provider_in: AIProviderUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    return await svc.update_provider(db, provider_id=provider_id, obj_in=provider_in, owner_id=None)


@router.delete("/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    force: bool = False,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Response:
    """管理员可删除任何服务商,包括用户的个人服务商。"""
    if await svc.delete_provider(db, provider_id=provider_id, force=force):
        await _reload_embedding()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/providers/{provider_id}/models", response_model=AIModelSchema)
async def create_ai_model(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    model_in: AIModelCreate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    return await svc.add_model(db, provider_id=provider_id, obj_in=model_in, owner_id=None)


@router.put("/models/{model_id}", response_model=AIModelSchema)
async def update_ai_model(
    *,
    db: AsyncSession = Depends(deps.get_db),
    model_id: int,
    model_in: AIModelUpdate,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    return await svc.update_model(db, model_id=model_id, obj_in=model_in, owner_id=None)


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ai_model(
    *,
    db: AsyncSession = Depends(deps.get_db),
    model_id: int,
    force: bool = False,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Response:
    if await svc.delete_model(db, model_id=model_id, force=force):
        await _reload_embedding()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# 个人服务商(任意登录用户,只能操作自己的)
# ---------------------------------------------------------------------------

@router.get("/me/providers", response_model=List[AIProviderSchema])
async def read_my_providers(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    return await svc.list_providers(db, user_id=current_user.id, only_owner=True)


@router.post("/me/providers", response_model=AIProviderSchema)
async def create_my_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_in: AIProviderCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    return await svc.create_provider(db, obj_in=provider_in, owner_id=current_user.id)


@router.put("/me/providers/{provider_id}", response_model=AIProviderSchema)
async def update_my_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    provider_in: AIProviderUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    return await svc.update_provider(
        db, provider_id=provider_id, obj_in=provider_in, owner_id=current_user.id
    )


@router.delete("/me/providers/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    current_user: User = Depends(deps.get_current_active_user),
) -> Response:
    await svc.get_provider_for(db, provider_id=provider_id, owner_id=current_user.id)
    await svc.delete_provider(db, provider_id=provider_id, force=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/me/providers/{provider_id}/models", response_model=AIModelSchema)
async def create_my_model(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    model_in: AIModelCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    return await svc.add_model(db, provider_id=provider_id, obj_in=model_in, owner_id=current_user.id)


@router.put("/me/models/{model_id}", response_model=AIModelSchema)
async def update_my_model(
    *,
    db: AsyncSession = Depends(deps.get_db),
    model_id: int,
    model_in: AIModelUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    return await svc.update_model(db, model_id=model_id, obj_in=model_in, owner_id=current_user.id)


@router.delete("/me/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_model(
    *,
    db: AsyncSession = Depends(deps.get_db),
    model_id: int,
    current_user: User = Depends(deps.get_current_active_user),
) -> Response:
    await svc.get_model_for(db, model_id=model_id, owner_id=current_user.id)
    await svc.delete_model(db, model_id=model_id, force=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _effective(db: AsyncSession, user_id: int, purpose: str) -> EffectiveModel:
    try:
        resolved = await resolve_model(db, user_id=user_id, purpose=purpose)  # type: ignore[arg-type]
    except Invalid as exc:
        return EffectiveModel(error=str(exc))
    if resolved is None:
        return EffectiveModel()
    return EffectiveModel(model_id=resolved.model.id, source=resolved.source)  # type: ignore[arg-type]


async def _preference_payload(db: AsyncSession, user_id: int) -> UserAIPreferenceSchema:
    pref = await svc.get_preferences(db, user_id=user_id)
    return UserAIPreferenceSchema(
        text_model_id=pref.text_model_id if pref else None,
        vision_model_id=pref.vision_model_id if pref else None,
        effective_text=await _effective(db, user_id, "text"),
        effective_vision=await _effective(db, user_id, "vision"),
    )


@router.get("/me/preferences", response_model=UserAIPreferenceSchema)
async def read_my_preferences(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    return await _preference_payload(db, current_user.id)


@router.put("/me/preferences", response_model=UserAIPreferenceSchema)
async def update_my_preferences(
    *,
    db: AsyncSession = Depends(deps.get_db),
    pref_in: UserAIPreferenceUpdate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    await svc.set_preferences(
        db,
        user_id=current_user.id,
        text_model_id=pref_in.text_model_id,
        vision_model_id=pref_in.vision_model_id,
    )
    return await _preference_payload(db, current_user.id)


# ---------------------------------------------------------------------------
# 连接测试 + 模型发现
# ---------------------------------------------------------------------------

@router.post("/discover-models", response_model=DiscoverModelsResponse)
async def discover_models(
    *,
    db: AsyncSession = Depends(deps.get_db),
    body: DiscoverModelsRequest,
    scope: str = "personal",
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """用填写的凭据(或已保存服务商的 Key)连一次服务商并列出模型。

    scope=global 时 provider_id 指全局服务商,需管理员;否则只能引用自己的服务商。
    """
    owner_id: Optional[int] = current_user.id
    if scope == "global":
        if not current_user.is_superuser:
            raise Forbidden("Not enough privileges", ErrorCode.AUTH_FORBIDDEN)
        owner_id = None
    return await svc.discover_models(
        db,
        interface_type=body.interface_type,
        base_url=body.base_url,
        api_key=body.api_key,
        provider_id=body.provider_id,
        owner_id=owner_id,
    )


# ---------------------------------------------------------------------------
# 全局场景分配
# ---------------------------------------------------------------------------

@router.get("/active-config")
async def get_active_config(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    def safe_int(val: str | None) -> int | None:
        if not val:
            return None
        try:
            return int(val)
        except ValueError:
            return None

    result = {}
    for field, key in (
        ("text_model_id", "AI_TEXT_MODEL_ID"),
        ("vision_model_id", "AI_VISION_MODEL_ID"),
        ("embedding_model_id", EMBEDDING_MODEL_KEY),
    ):
        setting = await system_setting.get_by_key(db, key)
        result[field] = safe_int(setting.value) if setting else None
    return result


@router.post("/active-config")
async def update_active_config(
    *,
    db: AsyncSession = Depends(deps.get_db),
    config: dict,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    fields = {
        "text_model_id": ("AI_TEXT_MODEL_ID", "Active AI Text Model ID"),
        "vision_model_id": ("AI_VISION_MODEL_ID", "Active AI Vision Model ID"),
        "embedding_model_id": (EMBEDDING_MODEL_KEY, "Active AI Embedding Model ID"),
    }
    embedding_changed = False
    for field, (key, description) in fields.items():
        if field not in config:
            continue
        raw_value = config[field]
        value = str(raw_value) if raw_value is not None else ""
        await validate_active_model(db, key=key, value=value)
        existing = await system_setting.get_by_key(db, key)
        if key == EMBEDDING_MODEL_KEY and (existing.value if existing else "") != value:
            embedding_changed = True
        if existing:
            existing.value = value
        else:
            from app.models.system_setting import SystemSetting
            db.add(SystemSetting(key=key, value=value, description=description))

    await db.commit()
    if embedding_changed:
        await _reload_embedding()

    return {"status": "success"}
