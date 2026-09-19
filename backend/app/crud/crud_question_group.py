from typing import Optional

from sqlalchemy import select
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


stimulus = CRUDStimulus(Stimulus)
question_group = CRUDQuestionGroup(QuestionGroup)