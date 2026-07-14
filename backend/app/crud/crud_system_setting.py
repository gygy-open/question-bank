from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.crud.base import CRUDBase
from app.models.system_setting import SystemSetting
from app.schemas.system_setting import SystemSettingCreate, SystemSettingUpdate

class CRUDSystemSetting(CRUDBase[SystemSetting, SystemSettingCreate, SystemSettingUpdate]):
    async def get_by_key(self, db: AsyncSession, key: str) -> Optional[SystemSetting]:
        return await db.get(self.model, key)

    async def get_map_by_keys(self, db: AsyncSession, keys: List[str]) -> Dict[str, str]:
        stmt = select(self.model).where(self.model.key.in_(keys))
        result = await db.execute(stmt)
        settings = result.scalars().all()
        return {s.key: s.value for s in settings if s.value}

    async def remove_by_key(self, db: AsyncSession, *, key: str) -> Optional[SystemSetting]:
        obj = await self.get_by_key(db, key)
        if obj:
            await db.delete(obj)
            await db.commit()
        return obj

system_setting = CRUDSystemSetting(SystemSetting)
