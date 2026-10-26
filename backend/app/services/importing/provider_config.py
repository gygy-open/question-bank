"""抽取阶段:AI provider 配置解析。

委托 app.services.ai_resolver:按 用户个人默认 → 全局激活 解析文本/视觉模型,
产出 provider 接口类型与调用 config(API_KEY/BASE_URL/MODEL_NAME)。
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_resolver import resolve_model


async def resolve_active_provider(
    db: AsyncSession, *, is_vision: bool = False, user_id: Optional[int] = None
) -> tuple[Optional[str], dict]:
    """返回 (provider_name, config);无可用配置时返回 (None, {})。"""
    resolved = await resolve_model(db, user_id=user_id, purpose="vision" if is_vision else "text")
    if resolved is None:
        return None, {}
    return resolved.interface_type, resolved.config
