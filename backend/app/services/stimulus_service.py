import json
from datetime import datetime
from typing import List, Optional, Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Conflict, NotFound, Unprocessable
from app.crud.crud_question import is_question_visible
from app.models.question import Question, QuestionVisibility
from app.models.stimulus import Stimulus
from app.models.user import User
from app.schemas.question import QuestionSummary
from app.schemas.stimulus import StimulusDetail, StimulusRead


def _is_private_hidden(resource: Stimulus, actor: User) -> bool:
    return (
        resource.visibility == QuestionVisibility.PRIVATE.value
        and not actor.is_superuser
        and resource.created_by != actor.id
    )


async def get_stimulus(db: AsyncSession, stimulus_id: int, actor: User) -> Stimulus:
    stimulus = await db.scalar(
        select(Stimulus)
        .where(Stimulus.id == stimulus_id, Stimulus.deleted_at.is_(None))
        .execution_options(populate_existing=True)
    )
    if stimulus is None or _is_private_hidden(stimulus, actor):
        raise NotFound("Stimulus not found")
    return stimulus


async def get_deleted_stimulus(db: AsyncSession, stimulus_id: int, actor: User) -> Stimulus:
    stimulus = await db.scalar(
        select(Stimulus)
        .where(Stimulus.id == stimulus_id, Stimulus.deleted_at.is_not(None))
        .execution_options(populate_existing=True)
    )
    if stimulus is None or _is_private_hidden(stimulus, actor):
        raise NotFound("Stimulus not found")
    return stimulus


async def list_stimulus_questions(
    db: AsyncSession, stimulus_id: int, actor: Optional[User] = None
) -> List[Question]:
    """材料下的活动小题,按 stimulus_position 排序;传入 actor 时过滤其不可见的私有题。"""
    result = await db.scalars(
        select(Question)
        .where(Question.stimulus_id == stimulus_id, Question.deleted_at.is_(None))
        .order_by(Question.stimulus_position, Question.id)
        .execution_options(populate_existing=True)
    )
    questions = list(result.all())
    if actor is None:
        return questions
    return [question for question in questions if is_question_visible(question, actor)]


async def to_detail(db: AsyncSession, stimulus: Stimulus, actor: User) -> StimulusDetail:
    questions = await list_stimulus_questions(db, stimulus.id, actor)
    return StimulusDetail(
        **StimulusRead.model_validate(stimulus).model_dump(),
        questions=[QuestionSummary.model_validate(question) for question in questions],
    )


async def next_stimulus_position(db: AsyncSession, stimulus_id: int) -> int:
    current = await db.scalar(
        select(func.max(Question.stimulus_position)).where(
            Question.stimulus_id == stimulus_id
        )
    )
    return 0 if current is None else int(current) + 1


async def bump_stimulus_revision(db: AsyncSession, stimulus_id: int) -> None:
    await db.execute(
        update(Stimulus)
        .where(Stimulus.id == stimulus_id)
        .values(revision=Stimulus.revision + 1, updated_at=datetime.utcnow())
    )


async def create_stimulus(
    db: AsyncSession,
    *,
    subject_id: int,
    content: dict,
    status_value: str,
    visibility: str,
    actor: User,
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Stimulus:
    stimulus = Stimulus(
        subject_id=subject_id,
        content=json.dumps(content, ensure_ascii=False),
        status=status_value,
        visibility=visibility,
        source=source,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(stimulus)
    await db.commit()
    await db.refresh(stimulus)
    return stimulus


async def update_stimulus(
    db: AsyncSession,
    *,
    stimulus: Stimulus,
    expected_revision: int,
    actor: User,
    content: Optional[dict] = None,
    status_value: Optional[str] = None,
    visibility: Optional[str] = None,
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Stimulus:
    values = {"updated_by": actor.id, "updated_at": datetime.utcnow()}
    content_revision = Stimulus.content_revision
    if content is not None:
        serialized = json.dumps(content, ensure_ascii=False)
        if serialized != stimulus.content:
            values["content"] = serialized
            content_revision = Stimulus.content_revision + 1
    if status_value is not None:
        values["status"] = status_value
    if visibility is not None:
        if visibility == QuestionVisibility.PRIVATE.value:
            public_question = await db.scalar(
                select(Question.id).where(
                    Question.stimulus_id == stimulus.id,
                    Question.deleted_at.is_(None),
                    Question.visibility == QuestionVisibility.PUBLIC.value,
                ).limit(1)
            )
            if public_question is not None:
                raise Unprocessable("材料下有公开小题，不能设为私有")
        values["visibility"] = visibility
    if source is not None:
        values["source"] = source
    if metadata is not None:
        values["metadata_json"] = json.dumps(metadata, ensure_ascii=False)
    result = await db.execute(
        update(Stimulus)
        .where(
            Stimulus.id == stimulus.id,
            Stimulus.revision == expected_revision,
            Stimulus.deleted_at.is_(None),
        )
        .values(**values, revision=Stimulus.revision + 1, content_revision=content_revision)
    )
    if result.rowcount == 0:
        raise Conflict("Stimulus revision mismatch")
    await db.commit()
    return await get_stimulus(db, stimulus.id, actor)


async def _lock_active_stimulus(
    db: AsyncSession, stimulus_id: int, expected_revision: int
) -> Stimulus:
    locked = await db.scalar(
        select(Stimulus)
        .where(Stimulus.id == stimulus_id, Stimulus.deleted_at.is_(None))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None or locked.revision != expected_revision:
        raise Conflict("Stimulus revision mismatch")
    return locked


async def delete_stimulus(
    db: AsyncSession, *, stimulus: Stimulus, expected_revision: int, actor: User
) -> None:
    locked = await _lock_active_stimulus(db, stimulus.id, expected_revision)
    if await list_stimulus_questions(db, locked.id):
        raise Unprocessable("题目材料下仍有小题，不能删除")
    locked.deleted_at = datetime.utcnow()
    locked.updated_by = actor.id
    locked.revision = locked.revision + 1
    await db.commit()


async def restore_stimulus(
    db: AsyncSession, *, stimulus: Stimulus, expected_revision: int, actor: User
) -> Stimulus:
    result = await db.execute(
        update(Stimulus)
        .where(
            Stimulus.id == stimulus.id,
            Stimulus.revision == expected_revision,
            Stimulus.deleted_at.is_not(None),
        )
        .values(
            deleted_at=None,
            updated_at=datetime.utcnow(),
            updated_by=actor.id,
            revision=Stimulus.revision + 1,
        )
    )
    if result.rowcount == 0:
        raise Conflict("Stimulus revision mismatch")
    await db.commit()
    return await get_stimulus(db, stimulus.id, actor)


def check_question_attachable(question: Question, stimulus: Stimulus) -> None:
    if question.subject_id != stimulus.subject_id:
        raise Unprocessable("材料与小题必须属于同一学科")
    if (
        question.visibility == QuestionVisibility.PUBLIC.value
        and stimulus.visibility == QuestionVisibility.PRIVATE.value
    ):
        raise Unprocessable("公开题目不能挂在私有材料下")


async def assign_positions(
    db: AsyncSession, stimulus_id: int, ordered: Sequence[Question]
) -> None:
    """按给定顺序重排材料小题;先清空位置再赋值,避开唯一约束的中间冲突。"""
    for question in ordered:
        question.stimulus_position = None
    await db.flush()
    for position, question in enumerate(ordered):
        question.stimulus_id = stimulus_id
        question.stimulus_position = position
    await db.flush()


async def set_stimulus_questions(
    db: AsyncSession,
    *,
    stimulus: Stimulus,
    expected_revision: int,
    question_ids: List[int],
    actor: User,
) -> StimulusDetail:
    locked = await _lock_active_stimulus(db, stimulus.id, expected_revision)
    requested: List[Question] = []
    if question_ids:
        rows = await db.scalars(
            select(Question)
            .where(Question.id.in_(question_ids), Question.deleted_at.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        by_id = {question.id: question for question in rows.all()}
        for question_id in question_ids:
            question = by_id.get(question_id)
            if question is None or not is_question_visible(question, actor):
                raise NotFound("Question not found")
            if question.stimulus_id not in (None, locked.id):
                raise Unprocessable(f"题目 {question_id} 已属于其他材料")
            check_question_attachable(question, locked)
            requested.append(question)

    current = await list_stimulus_questions(db, locked.id)
    requested_ids = set(question_ids)
    # 操作者看不见的他人私有小题不受本次编辑影响,保持原相对顺序排在末尾。
    hidden = [q for q in current if not is_question_visible(q, actor)]
    detached = [
        q for q in current if q.id not in requested_ids and is_question_visible(q, actor)
    ]
    for question in detached:
        question.stimulus_id = None
        question.stimulus_position = None
    await assign_positions(db, locked.id, [*requested, *hidden])
    locked.revision = locked.revision + 1
    locked.updated_by = actor.id
    await db.commit()
    return await to_detail(db, await get_stimulus(db, locked.id, actor), actor)
