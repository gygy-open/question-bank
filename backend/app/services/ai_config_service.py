from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Conflict, Invalid, NotFound
from app.models.ai_config import AIModel, AIProvider
from app.models.system_setting import SystemSetting


ACTIVE_MODEL_KEYS: Dict[str, str] = {
    "AI_TEXT_MODEL_ID": "文本模型",
    "AI_VISION_MODEL_ID": "视觉模型",
    "AI_EMBEDDING_MODEL_ID": "向量模型",
}
EMBEDDING_MODEL_KEY = "AI_EMBEDDING_MODEL_ID"


def _setting_model_id(setting: SystemSetting) -> int | None:
    if not setting.value:
        return None
    try:
        return int(setting.value)
    except ValueError:
        return None


async def validate_active_model(
    db: AsyncSession, *, key: str, value: str | None
) -> None:
    if key not in ACTIVE_MODEL_KEYS or not value:
        return
    try:
        model_id = int(value)
    except ValueError as exc:
        raise Invalid(f"{ACTIVE_MODEL_KEYS[key]} ID 必须是整数") from exc

    model = await db.scalar(
        select(AIModel).where(AIModel.id == model_id).with_for_update()
    )
    if model is None:
        raise Invalid(f"{ACTIVE_MODEL_KEYS[key]}不存在")
    if key == EMBEDDING_MODEL_KEY and not model.is_embedding_model:
        raise Invalid("所选模型不是向量模型")


async def _locked_active_settings(db: AsyncSession) -> List[SystemSetting]:
    result = await db.execute(
        select(SystemSetting)
        .where(SystemSetting.key.in_(ACTIVE_MODEL_KEYS))
        .with_for_update()
    )
    return list(result.scalars().all())


async def _clear_active_references(
    db: AsyncSession, *, model_ids: set[int], force: bool
) -> bool:
    settings = await _locked_active_settings(db)
    blocking = [
        setting
        for setting in settings
        if _setting_model_id(setting) in model_ids
    ]
    if blocking and not force:
        labels = "、".join(ACTIVE_MODEL_KEYS[setting.key] for setting in blocking)
        await db.rollback()
        raise Conflict(f"该配置仍被用作{labels}，确认停用后才能删除")

    for setting in blocking:
        setting.value = ""
    return any(setting.key == EMBEDDING_MODEL_KEY for setting in blocking)


async def delete_provider(
    db: AsyncSession, *, provider_id: int, force: bool = False
) -> bool:
    result = await db.execute(
        select(AIProvider)
        .options(selectinload(AIProvider.models))
        .where(AIProvider.id == provider_id)
        .with_for_update()
    )
    provider = result.scalar_one_or_none()
    if provider is None:
        await db.rollback()
        raise NotFound("Provider not found")

    await db.execute(
        select(AIModel)
        .where(AIModel.provider_id == provider_id)
        .with_for_update()
    )
    reload_embedding = await _clear_active_references(
        db, model_ids={model.id for model in provider.models}, force=force
    )
    await db.delete(provider)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("供应商仍被其他数据引用，暂时无法删除") from exc
    return reload_embedding


async def delete_model(
    db: AsyncSession, *, model_id: int, force: bool = False
) -> bool:
    model = await db.scalar(
        select(AIModel).where(AIModel.id == model_id).with_for_update()
    )
    if model is None:
        await db.rollback()
        raise NotFound("Model not found")

    reload_embedding = await _clear_active_references(
        db, model_ids={model.id}, force=force
    )
    await db.delete(model)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("模型仍被其他数据引用，暂时无法删除") from exc
    return reload_embedding