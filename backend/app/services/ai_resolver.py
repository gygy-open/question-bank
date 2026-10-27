"""统一的模型解析:谁能用哪个模型、某个场景该用哪个模型、调用配置怎么拼。

可用范围 = 全局服务商(owner_id 为空)+ 当前用户自己的服务商,且服务商处于启用状态。
场景解析顺序:调用方显式指定 → 用户个人默认 → 全局激活模型。
向量模型不走这里(索引全站共用,只能用全局配置,见 app.services.embedding)。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Invalid
from app.core.api_errors import ErrorCode
from app.core.secrets import SecretDecryptError, decrypt_secret
from app.models.ai_config import AIModel, AIProvider, UserAIPreference
from app.models.system_setting import SystemSetting

Purpose = Literal["text", "vision"]

GLOBAL_KEYS: dict[str, str] = {"text": "AI_TEXT_MODEL_ID", "vision": "AI_VISION_MODEL_ID"}
PREF_FIELDS: dict[str, str] = {"text": "text_model_id", "vision": "vision_model_id"}


@dataclass
class ResolvedModel:
    model: AIModel
    provider: AIProvider
    config: dict
    source: Literal["explicit", "personal", "global"]

    @property
    def interface_type(self) -> str:
        return self.provider.interface_type


def visible_to(user_id: Optional[int]):
    """服务商可见性条件:全局 + 自己的。"""
    if user_id is None:
        return AIProvider.owner_id.is_(None)
    return or_(AIProvider.owner_id.is_(None), AIProvider.owner_id == user_id)


def supports(model: AIModel, purpose: Purpose) -> bool:
    if model.is_embedding_model:
        return False
    if purpose == "vision":
        return bool(model.is_vision_capable)
    return True


def build_config(model: AIModel, provider: AIProvider) -> dict:
    try:
        api_key = decrypt_secret(provider.api_key)
    except SecretDecryptError as exc:
        raise Invalid(
            f"服务商「{provider.name}」的 API Key 无法解密，请重新填写",
            ErrorCode.AI_CONFIG_API_KEY_UNDECRYPTABLE,
            {"name": provider.name},
        ) from exc
    config = {"API_KEY": api_key, "MODEL_NAME": model.name}
    if provider.base_url:
        config["BASE_URL"] = provider.base_url
    return config


async def get_usable_model(
    db: AsyncSession, *, user_id: Optional[int], model_id: int, lock: bool = False
) -> Optional[AIModel]:
    """返回 user 可用(可见且服务商启用)的模型,否则 None。"""
    stmt = (
        select(AIModel)
        .join(AIProvider, AIModel.provider_id == AIProvider.id)
        .options(selectinload(AIModel.provider))
        .where(AIModel.id == model_id, AIProvider.is_active.is_not(False), visible_to(user_id))
    )
    if lock:
        stmt = stmt.with_for_update()
    return (await db.execute(stmt)).scalars().first()


async def _global_model_id(db: AsyncSession, purpose: Purpose) -> Optional[int]:
    setting = await db.get(SystemSetting, GLOBAL_KEYS[purpose])
    try:
        return int(setting.value) if setting and setting.value else None
    except ValueError:
        return None


async def _pref_model_id(db: AsyncSession, user_id: Optional[int], purpose: Purpose) -> Optional[int]:
    if user_id is None:
        return None
    pref = await db.get(UserAIPreference, user_id)
    return getattr(pref, PREF_FIELDS[purpose]) if pref else None


async def resolve_model(
    db: AsyncSession,
    *,
    user_id: Optional[int],
    purpose: Purpose = "text",
    model_id: Optional[int] = None,
    lock: bool = False,
) -> Optional[ResolvedModel]:
    """按 显式 → 个人默认 → 全局 解析;都不可用时返回 None。

    显式指定的模型不可用时直接报错,而不是悄悄换成别的模型。
    """
    if model_id is not None:
        model = await get_usable_model(db, user_id=user_id, model_id=model_id, lock=lock)
        if model is None:
            raise Invalid("所选模型不存在、已停用或无权使用", ErrorCode.AI_CONFIG_MODEL_UNUSABLE)
        if not supports(model, purpose):
            raise Invalid("所选模型不支持该用途", ErrorCode.AI_CONFIG_MODEL_PURPOSE_UNSUPPORTED)
        return ResolvedModel(model, model.provider, build_config(model, model.provider), "explicit")

    candidates = (
        ("personal", await _pref_model_id(db, user_id, purpose)),
        ("global", await _global_model_id(db, purpose)),
    )
    for source, candidate_id in candidates:
        if candidate_id is None:
            continue
        # 全局激活模型对所有人可用,按“全局可见”校验即可。
        scope_user = user_id if source == "personal" else None
        model = await get_usable_model(db, user_id=scope_user, model_id=candidate_id, lock=lock)
        if model is not None and supports(model, purpose):
            return ResolvedModel(model, model.provider, build_config(model, model.provider), source)  # type: ignore[arg-type]
    return None
