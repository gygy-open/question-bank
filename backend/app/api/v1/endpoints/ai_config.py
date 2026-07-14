from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.api import deps
from app.crud.crud_ai_config import ai_provider, ai_model
from app.crud.crud_system_setting import system_setting
from app.schemas.ai_config import AIProvider as AIProviderSchema, AIProviderCreate, AIProviderUpdate, AIModel as AIModelSchema, AIModelCreate
from app.schemas.system_setting import SystemSettingCreate, SystemSettingUpdate

router = APIRouter()

@router.get("/providers", response_model=List[AIProviderSchema])
async def read_ai_providers(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user = Depends(deps.get_current_active_user),
) -> Any:
    return await ai_provider.get_multi_with_models(db, skip=skip, limit=limit)

@router.post("/providers", response_model=AIProviderSchema)
async def create_ai_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_in: AIProviderCreate,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    return await ai_provider.create_with_models(db, obj_in=provider_in)

@router.put("/providers/{provider_id}", response_model=AIProviderSchema)
async def update_ai_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    provider_in: AIProviderUpdate,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    provider = await ai_provider.get(db, id=provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    provider = await ai_provider.update(db, db_obj=provider, obj_in=provider_in)
    return await ai_provider.get_with_models(db, id=provider.id)

@router.delete("/providers/{provider_id}", response_model=AIProviderSchema)
async def delete_ai_provider(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    provider = await ai_provider.get(db, id=provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return await ai_provider.remove(db, id=provider_id)

@router.post("/providers/{provider_id}/models", response_model=AIModelSchema)
async def create_ai_model(
    *,
    db: AsyncSession = Depends(deps.get_db),
    provider_id: int,
    model_in: AIModelCreate,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    provider = await ai_provider.get(db, id=provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    # Manually create model since CRUDBase doesn't handle child creation easily without custom logic
    from app.models.ai_config import AIModel
    db_model = AIModel(
        provider_id=provider_id,
        name=model_in.name,
        is_vision_capable=model_in.is_vision_capable,
        is_embedding_model=model_in.is_embedding_model
    )
    db.add(db_model)
    await db.commit()
    await db.refresh(db_model)
    return db_model

@router.delete("/models/{model_id}", response_model=AIModelSchema)
async def delete_ai_model(
    *,
    db: AsyncSession = Depends(deps.get_db),
    model_id: int,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    model = await ai_model.get(db, id=model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return await ai_model.remove(db, id=model_id)

@router.get("/active-config")
async def get_active_config(
    db: AsyncSession = Depends(deps.get_db),
    current_user = Depends(deps.get_current_active_user),
) -> Any:
    text_model_setting = await system_setting.get_by_key(db, "AI_TEXT_MODEL_ID")
    vision_model_setting = await system_setting.get_by_key(db, "AI_VISION_MODEL_ID")
    embedding_model_setting = await system_setting.get_by_key(db, "AI_EMBEDDING_MODEL_ID")
    
    def safe_int(val: str | None) -> int | None:
        if not val:
            return None
        try:
            return int(val)
        except ValueError:
            return None

    return {
        "text_model_id": safe_int(text_model_setting.value) if text_model_setting else None,
        "vision_model_id": safe_int(vision_model_setting.value) if vision_model_setting else None,
        "embedding_model_id": safe_int(embedding_model_setting.value) if embedding_model_setting else None
    }

@router.post("/active-config")
async def update_active_config(
    *,
    db: AsyncSession = Depends(deps.get_db),
    config: dict,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    if "text_model_id" in config:
        key = "AI_TEXT_MODEL_ID"
        raw_val = config["text_model_id"]
        val = str(raw_val) if raw_val is not None else ""
        existing = await system_setting.get_by_key(db, key)
        if existing:
            await system_setting.update(db, db_obj=existing, obj_in=SystemSettingUpdate(value=val))
        else:
            await system_setting.create(db, obj_in=SystemSettingCreate(key=key, value=val, description="Active AI Text Model ID"))
            
    if "vision_model_id" in config:
        key = "AI_VISION_MODEL_ID"
        raw_val = config["vision_model_id"]
        val = str(raw_val) if raw_val is not None else ""
        existing = await system_setting.get_by_key(db, key)
        if existing:
            await system_setting.update(db, db_obj=existing, obj_in=SystemSettingUpdate(value=val))
        else:
            await system_setting.create(db, obj_in=SystemSettingCreate(key=key, value=val, description="Active AI Vision Model ID"))

    if "embedding_model_id" in config:
        key = "AI_EMBEDDING_MODEL_ID"
        raw_val = config["embedding_model_id"]
        val = str(raw_val) if raw_val is not None else ""
        existing = await system_setting.get_by_key(db, key)
        if existing:
            await system_setting.update(db, db_obj=existing, obj_in=SystemSettingUpdate(value=val))
        else:
            await system_setting.create(db, obj_in=SystemSettingCreate(key=key, value=val, description="Active AI Embedding Model ID"))
    
    return {"status": "success"}
