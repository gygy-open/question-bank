from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select
from app.crud.base import CRUDBase
from app.models.system_setting import INTERNAL_KEY_PREFIXES, SystemSetting
from app.schemas.system_setting import SystemSettingCreate, SystemSettingUpdate

class CRUDSystemSetting(CRUDBase[SystemSetting, SystemSettingCreate, SystemSettingUpdate]):
    async def get_by_key(self, db: AsyncSession, key: str) -> Optional[SystemSetting]:
        return await db.get(self.model, key)

    async def get_multi_public(
        self, db: AsyncSession, *, skip: int = 0, limit: Optional[int] = 100
    ) -> List[SystemSetting]:
        """排除内部记录(见 INTERNAL_KEY_PREFIXES)的设置列表。"""
        stmt = (
            select(self.model)
            .where(and_(*(~self.model.key.startswith(p, autoescape=True) for p in INTERNAL_KEY_PREFIXES)))
            .offset(skip)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        return result.scalars().all()

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
