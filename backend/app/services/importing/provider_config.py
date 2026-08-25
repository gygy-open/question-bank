"""抽取阶段:AI provider 配置解析。

从 DB 动态配置(system_settings + ai_providers/ai_models)解析当前激活的
文本/视觉模型,产出 provider 名与调用 config(API_KEY/BASE_URL/MODEL_NAME)。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.crud_system_setting import system_setting
from app.models.ai_config import AIModel


async def resolve_active_provider(
    db: AsyncSession, *, is_vision: bool = False
) -> tuple[Optional[str], dict]:
    """返回 (provider_name, config);无激活配置时返回 (None, {})。"""
    setting_key = "AI_VISION_MODEL_ID" if is_vision else "AI_TEXT_MODEL_ID"
    setting = await system_setting.get_by_key(db, setting_key)
    if not setting or not setting.value:
        return None, {}

    try:
        model_id = int(setting.value)
    except ValueError:
        return None, {}

    stmt = select(AIModel).options(selectinload(AIModel.provider)).where(AIModel.id == model_id)
    result = await db.execute(stmt)
    model = result.scalar_one_or_none()
    if not model:
        return None, {}

    provider = model.provider
    return provider.interface_type, {
        "API_KEY": provider.api_key,
        "BASE_URL": provider.base_url,
        "MODEL_NAME": model.name,
    }
