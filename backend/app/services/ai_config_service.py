import asyncio
import re
from typing import Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Conflict, Invalid, NotFound
from app.core.api_errors import ErrorCode
from app.core.secrets import decrypt_secret, encrypt_secret
from app.models.ai_config import AIModel, AIProvider, UserAIPreference
from app.models.system_setting import SystemSetting


ACTIVE_MODEL_KEYS: Dict[str, str] = {
    "AI_TEXT_MODEL_ID": "文本模型",
    "AI_VISION_MODEL_ID": "视觉模型",
    "AI_EMBEDDING_MODEL_ID": "向量模型",
}
EMBEDDING_MODEL_KEY = "AI_EMBEDDING_MODEL_ID"
# 前端按 apiErrors.refs.<值> 翻译这些槽位名(见 frontend/app/lib/apiErrors.ts 的 *_ref 参数约定)。
ACTIVE_MODEL_SLOT_REFS: Dict[str, str] = {
    "AI_TEXT_MODEL_ID": "model_slot.text",
    "AI_VISION_MODEL_ID": "model_slot.vision",
    "AI_EMBEDDING_MODEL_ID": "model_slot.embedding",
}


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
        raise Invalid(
            f"{ACTIVE_MODEL_KEYS[key]} ID 必须是整数",
            ErrorCode.AI_CONFIG_ACTIVE_ID_INVALID,
            {"target_ref": ACTIVE_MODEL_SLOT_REFS[key]},
        ) from exc

    model = await db.scalar(
        select(AIModel).where(AIModel.id == model_id).with_for_update()
    )
    if model is None:
        raise Invalid(
            f"{ACTIVE_MODEL_KEYS[key]}不存在",
            ErrorCode.AI_CONFIG_ACTIVE_MODEL_NOT_FOUND,
            {"target_ref": ACTIVE_MODEL_SLOT_REFS[key]},
        )
    provider = await db.get(AIProvider, model.provider_id)
    # 个人服务商的 Key 只属于其主人,不能被提升为全站共用。
    if provider is None or provider.owner_id is not None:
        raise Invalid("只能选择全局服务商下的模型", ErrorCode.AI_CONFIG_GLOBAL_PROVIDER_ONLY)
    if key == EMBEDDING_MODEL_KEY:
        if not model.is_embedding_model:
            raise Invalid("所选模型不是向量模型", ErrorCode.AI_CONFIG_NOT_EMBEDDING_MODEL)
    elif model.is_embedding_model:
        raise Invalid("向量模型不能用于文本或识图", ErrorCode.AI_CONFIG_EMBEDDING_NOT_FOR_TEXT_VISION)
    elif key == "AI_VISION_MODEL_ID" and not model.is_vision_capable:
        raise Invalid("所选模型不支持识图", ErrorCode.AI_CONFIG_MODEL_NO_VISION)


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
        refs = ",".join(ACTIVE_MODEL_SLOT_REFS[setting.key] for setting in blocking)
        await db.rollback()
        raise Conflict(
            f"该配置仍被用作{labels}，确认停用后才能删除",
            ErrorCode.AI_CONFIG_IN_USE_CONFIRM,
            {"targets_ref": refs},
        )

    for setting in blocking:
        setting.value = ""
    await _clear_preferences(db, model_ids=model_ids)
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
        raise NotFound("Provider not found", ErrorCode.AI_CONFIG_PROVIDER_NOT_FOUND)

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
        raise Conflict("供应商仍被其他数据引用，暂时无法删除", ErrorCode.AI_CONFIG_PROVIDER_IN_USE) from exc
    return reload_embedding


async def delete_model(
    db: AsyncSession, *, model_id: int, force: bool = False
) -> bool:
    model = await db.scalar(
        select(AIModel).where(AIModel.id == model_id).with_for_update()
    )
    if model is None:
        await db.rollback()
        raise NotFound("Model not found", ErrorCode.AI_CONFIG_MODEL_NOT_FOUND)

    reload_embedding = await _clear_active_references(
        db, model_ids={model.id}, force=force
    )
    await db.delete(model)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise Conflict("模型仍被其他数据引用，暂时无法删除", ErrorCode.AI_CONFIG_MODEL_IN_USE) from exc
    return reload_embedding


async def _clear_preferences(db: AsyncSession, *, model_ids: set[int]) -> None:
    """外键已是 SET NULL;这里显式清一遍,不依赖具体数据库是否开启外键约束。"""
    if not model_ids:
        return
    for field in (UserAIPreference.text_model_id, UserAIPreference.vision_model_id):
        await db.execute(
            update(UserAIPreference).where(field.in_(model_ids)).values({field.key: None})
        )


# ---------------------------------------------------------------------------
# 服务商 / 模型维护(全局与个人共用;owner_id=None 表示全局)
# ---------------------------------------------------------------------------

INTERFACE_TYPES = {"openai", "gemini"}


def _check_interface(interface_type: Optional[str]) -> None:
    if interface_type is not None and interface_type not in INTERFACE_TYPES:
        raise Invalid("不支持的服务类型", ErrorCode.AI_CONFIG_UNSUPPORTED_INTERFACE)


async def ensure_unique_name(
    db: AsyncSession, *, name: str, owner_id: Optional[int], exclude_id: Optional[int] = None
) -> None:
    owner_cond = AIProvider.owner_id.is_(None) if owner_id is None else AIProvider.owner_id == owner_id
    stmt = select(AIProvider.id).where(AIProvider.name == name, owner_cond)
    if exclude_id is not None:
        stmt = stmt.where(AIProvider.id != exclude_id)
    if await db.scalar(stmt) is not None:
        raise Conflict(f"已存在名为「{name}」的服务商", ErrorCode.AI_CONFIG_PROVIDER_NAME_TAKEN, {"name": name})


async def get_provider_for(
    db: AsyncSession, *, provider_id: int, owner_id: Optional[int], lock: bool = False
) -> AIProvider:
    """按归属取服务商;归属不符一律 404,不泄露别人的服务商是否存在。"""
    stmt = select(AIProvider).options(selectinload(AIProvider.models)).where(AIProvider.id == provider_id)
    if lock:
        stmt = stmt.with_for_update()
    provider = (await db.execute(stmt)).scalar_one_or_none()
    if provider is None or provider.owner_id != owner_id:
        raise NotFound("Provider not found", ErrorCode.AI_CONFIG_PROVIDER_NOT_FOUND)
    return provider


async def get_model_for(db: AsyncSession, *, model_id: int, owner_id: Optional[int]) -> AIModel:
    model = await db.scalar(
        select(AIModel).options(selectinload(AIModel.provider)).where(AIModel.id == model_id)
    )
    if model is None or model.provider.owner_id != owner_id:
        raise NotFound("Model not found", ErrorCode.AI_CONFIG_MODEL_NOT_FOUND)
    return model


async def list_providers(
    db: AsyncSession, *, user_id: Optional[int], include_all: bool = False, only_owner: bool = False
) -> List[AIProvider]:
    stmt = select(AIProvider).options(selectinload(AIProvider.models), selectinload(AIProvider.owner))
    if only_owner:
        stmt = stmt.where(AIProvider.owner_id == user_id)
    elif not include_all:
        stmt = stmt.where(
            (AIProvider.owner_id.is_(None)) | (AIProvider.owner_id == user_id)
            if user_id is not None
            else AIProvider.owner_id.is_(None)
        )
    stmt = stmt.order_by(AIProvider.owner_id.is_not(None), AIProvider.id)
    return list((await db.execute(stmt)).scalars().all())


async def create_provider(db: AsyncSession, *, obj_in, owner_id: Optional[int]) -> AIProvider:
    _check_interface(obj_in.interface_type)
    if not obj_in.api_key:
        raise Invalid("请填写 API Key", ErrorCode.AI_CONFIG_API_KEY_REQUIRED)
    await ensure_unique_name(db, name=obj_in.name, owner_id=owner_id)
    provider = AIProvider(
        name=obj_in.name,
        interface_type=obj_in.interface_type,
        base_url=obj_in.base_url or None,
        api_key=encrypt_secret(obj_in.api_key),
        is_active=obj_in.is_active,
        owner_id=owner_id,
    )
    db.add(provider)
    await db.flush()
    seen: set[str] = set()
    for model_in in obj_in.models:
        name = model_in.name.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        db.add(AIModel(
            provider_id=provider.id,
            name=name,
            is_vision_capable=model_in.is_vision_capable,
            is_embedding_model=model_in.is_embedding_model,
        ))
    await db.commit()
    return await get_provider_for(db, provider_id=provider.id, owner_id=owner_id)


async def update_provider(
    db: AsyncSession, *, provider_id: int, obj_in, owner_id: Optional[int]
) -> AIProvider:
    provider = await get_provider_for(db, provider_id=provider_id, owner_id=owner_id, lock=True)
    data = obj_in.model_dump(exclude_unset=True)
    _check_interface(data.get("interface_type"))
    if data.get("name") and data["name"] != provider.name:
        await ensure_unique_name(db, name=data["name"], owner_id=owner_id, exclude_id=provider.id)
    api_key = data.pop("api_key", None)
    if api_key:  # 留空 = 不修改
        provider.api_key = encrypt_secret(api_key)
    if "base_url" in data:
        data["base_url"] = data["base_url"] or None
    for field, value in data.items():
        if value is not None or field == "base_url":
            setattr(provider, field, value)
    await db.commit()
    db.expire(provider)
    return await get_provider_for(db, provider_id=provider_id, owner_id=owner_id)


async def add_model(
    db: AsyncSession, *, provider_id: int, obj_in, owner_id: Optional[int]
) -> AIModel:
    provider = await get_provider_for(db, provider_id=provider_id, owner_id=owner_id)
    name = obj_in.name.strip()
    if not name:
        raise Invalid("请填写模型名称", ErrorCode.AI_CONFIG_MODEL_NAME_REQUIRED)
    if any(m.name == name for m in provider.models):
        raise Conflict(f"模型「{name}」已存在", ErrorCode.AI_CONFIG_MODEL_NAME_TAKEN, {"name": name})
    model = AIModel(
        provider_id=provider.id,
        name=name,
        is_vision_capable=obj_in.is_vision_capable,
        is_embedding_model=obj_in.is_embedding_model,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)
    return model


async def update_model(
    db: AsyncSession, *, model_id: int, obj_in, owner_id: Optional[int]
) -> AIModel:
    model = await get_model_for(db, model_id=model_id, owner_id=owner_id)
    data = obj_in.model_dump(exclude_unset=True, exclude_none=True)
    if "name" in data:
        data["name"] = data["name"].strip()
        if not data["name"]:
            raise Invalid("请填写模型名称", ErrorCode.AI_CONFIG_MODEL_NAME_REQUIRED)
    for field, value in data.items():
        setattr(model, field, value)

    # 改了能力标签后,不能让它继续占着不再胜任的场景。
    settings = await _locked_active_settings(db)
    for setting in settings:
        if _setting_model_id(setting) != model.id:
            continue
        if setting.key == EMBEDDING_MODEL_KEY and not model.is_embedding_model:
            raise Conflict("该模型正被用作向量模型，不能取消“向量”标记", ErrorCode.AI_CONFIG_EMBEDDING_FLAG_LOCKED)
        if setting.key != EMBEDDING_MODEL_KEY and model.is_embedding_model:
            raise Conflict(
                f"该模型正被用作{ACTIVE_MODEL_KEYS[setting.key]}，不能标记为向量模型",
                ErrorCode.AI_CONFIG_CANNOT_BECOME_EMBEDDING,
                {"target_ref": ACTIVE_MODEL_SLOT_REFS[setting.key]},
            )
        if setting.key == "AI_VISION_MODEL_ID" and not model.is_vision_capable:
            raise Conflict("该模型正被用作识图模型，不能取消“识图”标记", ErrorCode.AI_CONFIG_VISION_FLAG_LOCKED)
    await db.commit()
    await db.refresh(model)
    return model


async def get_preferences(db: AsyncSession, *, user_id: int) -> Optional[UserAIPreference]:
    return await db.get(UserAIPreference, user_id)


async def set_preferences(
    db: AsyncSession, *, user_id: int, text_model_id: Optional[int], vision_model_id: Optional[int]
) -> UserAIPreference:
    from app.services.ai_resolver import get_usable_model, supports

    for purpose, model_id in (("text", text_model_id), ("vision", vision_model_id)):
        if model_id is None:
            continue
        model = await get_usable_model(db, user_id=user_id, model_id=model_id)
        if model is None:
            raise Invalid("所选模型不存在、已停用或无权使用", ErrorCode.AI_CONFIG_MODEL_UNUSABLE)
        if not supports(model, purpose):  # type: ignore[arg-type]
            if purpose == "text":
                raise Invalid("向量模型不能用于文本", ErrorCode.AI_CONFIG_EMBEDDING_NOT_FOR_TEXT)
            raise Invalid("所选模型不支持识图", ErrorCode.AI_CONFIG_MODEL_NO_VISION)

    pref = await db.get(UserAIPreference, user_id)
    if pref is None:
        pref = UserAIPreference(user_id=user_id)
        db.add(pref)
    pref.text_model_id = text_model_id
    pref.vision_model_id = vision_model_id
    await db.commit()
    await db.refresh(pref)
    return pref


# ---------------------------------------------------------------------------
# 降低配置门槛:能力推断、连通性测试、模型发现
# ---------------------------------------------------------------------------

_EMBEDDING_RE = re.compile(r"embed|bge-|\bbge\b|m3e|gte-", re.I)
_VISION_RE = re.compile(
    r"vision|[-_.]vl\b|[-_]vl[-_]|qvq|4o|gpt-4\.1|gpt-4-turbo|gpt-5|\bo[34]\b|gemini|claude-3|claude-(sonnet|opus|haiku)"
    r"|glm-4v|glm-4\.\dv|llava|pixtral|internvl|kimi-.*vision|moonshot-.*vision|doubao-.*vision",
    re.I,
)


def guess_capabilities(model_name: str) -> dict:
    """按模型名推断能力,只作为默认勾选值,用户可改。"""
    if _EMBEDDING_RE.search(model_name):
        return {"is_vision_capable": False, "is_embedding_model": True}
    return {"is_vision_capable": bool(_VISION_RE.search(model_name)), "is_embedding_model": False}


CONNECT_TIMEOUT_SECONDS = 15.0


async def _list_remote_models(interface_type: str, base_url: Optional[str], api_key: str) -> List[str]:
    if interface_type == "gemini":
        import google.genai as genai

        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["http_options"] = {"base_url": base_url}
        client = genai.Client(**kwargs)
        names: List[str] = []
        pager = await client.aio.models.list()
        async for item in pager:
            name = (item.name or "").removeprefix("models/")
            if name:
                names.append(name)
        return names

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url or None, timeout=CONNECT_TIMEOUT_SECONDS, max_retries=0)
    page = await client.models.list()
    return [m.id for m in page.data]


async def _resolve_credentials(
    db: AsyncSession,
    *,
    interface_type: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
    provider_id: Optional[int],
    owner_id: Optional[int],
) -> tuple[str, Optional[str], str]:
    """表单里没重填 Key 时,用已保存服务商的 Key(须有权管理该服务商)。"""
    if provider_id is not None:
        provider = await get_provider_for(db, provider_id=provider_id, owner_id=owner_id)
        interface_type = interface_type or provider.interface_type
        base_url = base_url if base_url is not None else provider.base_url
        api_key = api_key or decrypt_secret(provider.api_key)
    _check_interface(interface_type)
    if not interface_type or not api_key:
        raise Invalid("请填写服务类型和 API Key", ErrorCode.AI_CONFIG_INTERFACE_AND_KEY_REQUIRED)
    return interface_type, (base_url or None), api_key


def _friendly_error(exc: Exception) -> str:
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status in (401, 403):
        return "API Key 无效或没有权限"
    if status == 404:
        return "接口地址不正确（找不到模型列表接口）"
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)) or "timeout" in type(exc).__name__.lower():
        return "连接超时，请检查接口地址或网络"
    if "connect" in type(exc).__name__.lower():
        return "无法连接到接口地址"
    return str(exc)[:200] or type(exc).__name__


async def discover_models(
    db: AsyncSession,
    *,
    interface_type: Optional[str],
    base_url: Optional[str],
    api_key: Optional[str],
    provider_id: Optional[int],
    owner_id: Optional[int],
) -> dict:
    """测试连接并拉取模型列表。返回 {ok, message, models:[{name, ...能力推断}]}。"""
    interface_type, base_url, api_key = await _resolve_credentials(
        db, interface_type=interface_type, base_url=base_url, api_key=api_key,
        provider_id=provider_id, owner_id=owner_id,
    )
    try:
        names = await asyncio.wait_for(
            _list_remote_models(interface_type, base_url, api_key), timeout=CONNECT_TIMEOUT_SECONDS
        )
    except Exception as exc:  # noqa: BLE001 - 外部服务的任何失败都转成可读提示
        return {"ok": False, "message": _friendly_error(exc), "models": []}
    models = [{"name": n, **guess_capabilities(n)} for n in sorted(set(names))]
    return {"ok": True, "message": f"连接成功，发现 {len(models)} 个模型", "models": models}
