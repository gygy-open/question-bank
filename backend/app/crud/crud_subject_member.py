from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.subject_member import SubjectMember


class CRUDSubjectMember:
    async def list_by_subject(self, db: AsyncSession, *, subject_id: int) -> list[SubjectMember]:
        result = await db.execute(
            select(SubjectMember)
            .options(selectinload(SubjectMember.user))
            .filter(SubjectMember.subject_id == subject_id)
            .order_by(SubjectMember.id)
        )
        return list(result.scalars().all())

    async def get(
        self, db: AsyncSession, *, user_id: int, subject_id: int
    ) -> Optional[SubjectMember]:
        result = await db.execute(
            select(SubjectMember)
            .options(selectinload(SubjectMember.user))
            .filter(
                SubjectMember.user_id == user_id,
                SubjectMember.subject_id == subject_id,
            )
        )
        return result.scalars().first()

    async def set_role(
        self, db: AsyncSession, *, user_id: int, subject_id: int, role: str
    ) -> SubjectMember:
        """按 (user, subject) upsert 角色。"""
        member = await self.get(db, user_id=user_id, subject_id=subject_id)
        if member is None:
            member = SubjectMember(user_id=user_id, subject_id=subject_id, role=role)
            db.add(member)
        else:
            member.role = role
        await db.commit()
        await db.refresh(member)
        return member

    async def remove_member(
        self, db: AsyncSession, *, user_id: int, subject_id: int
    ) -> bool:
        member = await self.get(db, user_id=user_id, subject_id=subject_id)
        if member is None:
            return False
        await db.delete(member)
        await db.commit()
        return True


subject_member = CRUDSubjectMember()
