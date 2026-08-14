from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.subject_prompt import SubjectPrompt


class CRUDSubjectPrompt:
    async def get(
        self, db: AsyncSession, subject_id: int, key: str
    ) -> Optional[SubjectPrompt]:
        result = await db.execute(
            select(SubjectPrompt).where(
                SubjectPrompt.subject_id == subject_id, SubjectPrompt.key == key
            )
        )
        return result.scalar_one_or_none()

    async def get_value(
        self, db: AsyncSession, subject_id: int, key: str
    ) -> Optional[str]:
        obj = await self.get(db, subject_id, key)
        return obj.value if obj else None

    async def upsert(
        self, db: AsyncSession, subject_id: int, key: str, value: str
    ) -> SubjectPrompt:
        obj = await self.get(db, subject_id, key)
        if obj:
            obj.value = value
            db.add(obj)
        else:
            obj = SubjectPrompt(subject_id=subject_id, key=key, value=value)
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


subject_prompt = CRUDSubjectPrompt()
