from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subject_setting import SubjectSetting


class CRUDSubjectSetting:
    async def get(
        self, db: AsyncSession, subject_id: int, key: str
    ) -> Optional[SubjectSetting]:
        result = await db.execute(
            select(SubjectSetting).where(
                SubjectSetting.subject_id == subject_id, SubjectSetting.key == key
            )
        )
        return result.scalar_one_or_none()

    async def get_value(
        self, db: AsyncSession, subject_id: int, key: str
    ) -> Optional[Any]:
        obj = await self.get(db, subject_id, key)
        return obj.value if obj else None

    async def upsert(
        self, db: AsyncSession, subject_id: int, key: str, value: Any
    ) -> SubjectSetting:
        obj = await self.get(db, subject_id, key)
        if obj:
            obj.value = value
            db.add(obj)
        else:
            obj = SubjectSetting(subject_id=subject_id, key=key, value=value)
            db.add(obj)
        await db.commit()
        await db.refresh(obj)
        return obj

    async def remove(self, db: AsyncSession, subject_id: int, key: str) -> bool:
        obj = await self.get(db, subject_id, key)
        if not obj:
            return False
        await db.delete(obj)
        await db.commit()
        return True


subject_setting = CRUDSubjectSetting()
