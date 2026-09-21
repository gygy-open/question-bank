from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.crud.base import CRUDBase
from app.models.question_group import QuestionGroup, QuestionGroupItem, Stimulus
from app.schemas.question_group import (
    QuestionGroupCreate,
    QuestionGroupUpdate,
    StimulusCreate,
    StimulusUpdate,
)


class CRUDStimulus(CRUDBase[Stimulus, StimulusCreate, StimulusUpdate]):
    async def get_active(self, db: AsyncSession, id: int) -> Optional[Stimulus]:
        result = await db.execute(
            select(Stimulus).where(Stimulus.id == id, Stimulus.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_deleted(self, db: AsyncSession, id: int) -> Optional[Stimulus]:
        result = await db.execute(
            select(Stimulus).where(Stimulus.id == id, Stimulus.deleted_at.is_not(None))
        )
        return result.scalar_one_or_none()

    async def get_page(
        self,
        db: AsyncSession,
        *,
        subject_id: int,
        viewer_id: int,
        is_superuser: bool,
        skip: int,
        limit: int,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        only_deleted: bool = False,
    ) -> tuple[List[tuple[Stimulus, int]], int]:
        conditions = [
            Stimulus.subject_id == subject_id,
            Stimulus.deleted_at.is_not(None)
            if only_deleted
            else Stimulus.deleted_at.is_(None),
        ]
        if not is_superuser:
            conditions.append(
                or_(Stimulus.visibility == "public", Stimulus.created_by == viewer_id)
            )
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(Stimulus.content.ilike(pattern), Stimulus.source.ilike(pattern))
            )
        if status:
            conditions.append(Stimulus.status == status)
        if visibility:
            conditions.append(Stimulus.visibility == visibility)

        total = await db.scalar(
            select(func.count()).select_from(Stimulus).where(*conditions)
        )
        active_group_count = (
            select(func.count(QuestionGroup.id))
            .where(
                QuestionGroup.stimulus_id == Stimulus.id,
                QuestionGroup.deleted_at.is_(None),
            )
            .correlate(Stimulus)
            .scalar_subquery()
        )
        result = await db.execute(
            select(Stimulus, active_group_count)
            .where(*conditions)
            .order_by(Stimulus.updated_at.desc(), Stimulus.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()], int(total or 0)


class CRUDQuestionGroup(CRUDBase[QuestionGroup, QuestionGroupCreate, QuestionGroupUpdate]):
    async def get_active(self, db: AsyncSession, id: int) -> Optional[QuestionGroup]:
        result = await db.execute(
            select(QuestionGroup)
            .execution_options(populate_existing=True)
            .options(
                selectinload(QuestionGroup.stimulus),
                selectinload(QuestionGroup.items).selectinload(QuestionGroupItem.question),
            )
            .where(QuestionGroup.id == id, QuestionGroup.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_deleted(self, db: AsyncSession, id: int) -> Optional[QuestionGroup]:
        result = await db.execute(
            select(QuestionGroup)
            .execution_options(populate_existing=True)
            .options(
                selectinload(QuestionGroup.stimulus),
                selectinload(QuestionGroup.items).selectinload(QuestionGroupItem.question),
            )
            .where(QuestionGroup.id == id, QuestionGroup.deleted_at.is_not(None))
        )
        return result.scalar_one_or_none()

    async def get_page(
        self,
        db: AsyncSession,
        *,
        subject_id: int,
        viewer_id: int,
        is_superuser: bool,
        skip: int,
        limit: int,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        stimulus_id: Optional[int] = None,
        question_id: Optional[int] = None,
        only_deleted: bool = False,
    ) -> tuple[List[QuestionGroup], int]:
        conditions = [
            QuestionGroup.subject_id == subject_id,
            QuestionGroup.deleted_at.is_not(None)
            if only_deleted
            else QuestionGroup.deleted_at.is_(None),
        ]
        if not is_superuser:
            conditions.append(
                or_(
                    QuestionGroup.visibility == "public",
                    QuestionGroup.created_by == viewer_id,
                )
            )
        if keyword:
            pattern = f"%{keyword}%"
            conditions.append(
                or_(
                    QuestionGroup.source.ilike(pattern),
                    QuestionGroup.stimulus.has(Stimulus.content.ilike(pattern)),
                )
            )
        if status:
            conditions.append(QuestionGroup.status == status)
        if visibility:
            conditions.append(QuestionGroup.visibility == visibility)
        if stimulus_id is not None:
            conditions.append(QuestionGroup.stimulus_id == stimulus_id)
        if question_id is not None:
            conditions.append(
                QuestionGroup.items.any(QuestionGroupItem.question_id == question_id)
            )

        total = await db.scalar(
            select(func.count()).select_from(QuestionGroup).where(*conditions)
        )
        result = await db.execute(
            select(QuestionGroup)
            .execution_options(populate_existing=True)
            .options(
                selectinload(QuestionGroup.stimulus),
                selectinload(QuestionGroup.items).selectinload(QuestionGroupItem.question),
            )
            .where(*conditions)
            .order_by(QuestionGroup.updated_at.desc(), QuestionGroup.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)


stimulus = CRUDStimulus(Stimulus)
question_group = CRUDQuestionGroup(QuestionGroup)