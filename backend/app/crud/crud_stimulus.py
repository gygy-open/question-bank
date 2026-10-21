from typing import Any, List, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.composition import Composition, CompositionNode, ScopeType
from app.models.question import Question
from app.models.stimulus import Stimulus
from app.schemas.stimulus import StimulusCreate, StimulusUpdate


def composition_usage_count(stimulus_id: Any, *, viewer_id: int, is_superuser: bool):
    """引用该材料的未删除稿件数;只统计查看者看得到的(共享或本人个人稿)。"""
    conditions = [CompositionNode.stimulus_id == stimulus_id, Composition.deleted_at.is_(None)]
    if not is_superuser:
        conditions.append(
            or_(Composition.scope_type == ScopeType.SHARED, Composition.owner_id == viewer_id)
        )
    return (
        select(func.count(func.distinct(CompositionNode.composition_id)))
        .join(Composition, Composition.id == CompositionNode.composition_id)
        .where(and_(*conditions))
    )


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
        has_questions: Optional[bool] = None,
    ) -> tuple[List[tuple[Stimulus, int, int]], int]:
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

        active_question_count = (
            select(func.count(Question.id))
            .where(
                Question.stimulus_id == Stimulus.id,
                Question.deleted_at.is_(None),
            )
            .correlate(Stimulus)
            .scalar_subquery()
        )
        if has_questions is not None:
            conditions.append(active_question_count > 0 if has_questions else active_question_count == 0)

        total = await db.scalar(
            select(func.count()).select_from(Stimulus).where(*conditions)
        )
        used_by = (
            composition_usage_count(Stimulus.id, viewer_id=viewer_id, is_superuser=is_superuser)
            .correlate(Stimulus)
            .scalar_subquery()
        )
        result = await db.execute(
            select(Stimulus, active_question_count, used_by)
            .where(*conditions)
            .order_by(Stimulus.updated_at.desc(), Stimulus.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return [(row[0], row[1], row[2]) for row in result.all()], int(total or 0)


stimulus = CRUDStimulus(Stimulus)
