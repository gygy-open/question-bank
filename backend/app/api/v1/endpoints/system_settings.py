from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from app import crud, models, schemas
from app.api import deps
from app.services.embedding import reload_embedding_function

router = APIRouter()

@router.get("", response_model=List[schemas.SystemSetting])
async def read_system_settings(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_superuser),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve system settings. Only for superusers.
    """
    settings = await crud.system_setting.get_multi(db, skip=skip, limit=limit)
    return settings

@router.put("/{key}", response_model=schemas.SystemSetting)
async def update_system_setting(
    *,
    db: deps.SessionDep,
    key: str,
    setting_in: schemas.SystemSettingUpdate,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a system setting. Only for superusers.
    """
    setting = await crud.system_setting.get_by_key(db, key=key)
    if not setting:
        # Allow creating if not exists, or raise 404. 
        # Since we want to support adding new settings via API potentially (or just updating),
        # let's check if the user wants to create.
        # But the requirement says "管理员可以设置", usually implies update.
        # However, if we want to add new keys dynamically, we might need a create endpoint or upsert here.
        # Let's do upsert logic for PUT.
        setting_create = schemas.SystemSettingCreate(key=key, **setting_in.model_dump())
        setting = await crud.system_setting.create(db, obj_in=setting_create)
    else:
        setting = await crud.system_setting.update(db, db_obj=setting, obj_in=setting_in)

    if key == "AI_EMBEDDING_MODEL_ID":
        await reload_embedding_function()

    return setting
