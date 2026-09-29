from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.question import Question
from app.models.stimulus import Stimulus
from app.schemas.stimulus import StimulusCreate, StimulusUpdate


class CRUDStimulus(CRUDBase[Stimulus, StimulusCreate, StimulusUpdate]):
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
        active_question_count = (
            select(func.count(Question.id))
            .where(
                Question.stimulus_id == Stimulus.id,
                Question.deleted_at.is_(None),
            )
            .correlate(Stimulus)
            .scalar_subquery()
        )
        result = await db.execute(
            select(Stimulus, active_question_count)
            .where(*conditions)
            .order_by(Stimulus.updated_at.desc(), Stimulus.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in result.all()], int(total or 0)


stimulus = CRUDStimulus(Stimulus)
