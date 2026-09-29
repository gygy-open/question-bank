from typing import List

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Conflict, Forbidden, Invalid, NotFound, Unprocessable
from app.core import permissions
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible
from app.models.question import Question
from app.models.question_relation import QuestionRelation, QuestionRelationType
from app.models.user import User
from app.schemas.question_relation import (
    QuestionRelationPeerRead,
    QuestionRelationQuestionRead,
    QuestionRelationsRead,
)



async def create_question_relation(
    db: AsyncSession,
    *,
    source_question_id: int,
    target_question_id: int,
    actor: User,
    commit: bool = True,
    new_target: bool = False,
) -> QuestionRelation:
    """Create an edge through the sole transactional graph-write entrypoint.

    A database constraint cannot express graph reachability. The subject-wide
    question lock serializes MySQL writers before duplicate and cycle checks;
    SQLite's single-writer transaction provides the conservative fallback.
    """
    if source_question_id == target_question_id:
        raise Invalid("Question relation cannot reference itself")
    result = await db.execute(
        select(Question).where(
            Question.id.in_([source_question_id, target_question_id]),
            Question.deleted_at.is_(None),
        )
    )
    questions = list(result.scalars().all())
    if len(questions) != 2:
        raise NotFound("Question not found")
    if questions[0].subject_id != questions[1].subject_id:
        raise Unprocessable("Question relation endpoints must share a subject")
    subject_id = questions[0].subject_id
    if not permissions.can(actor, Permission.EDIT_QUESTION, subject_id=subject_id):
        raise Forbidden("The user doesn't have enough privileges")
    if any(not is_question_visible(question, actor) for question in questions):
        raise NotFound("Question not found")

    # Existing graph writes serialize by subject so concurrent multi-edge writes
    # cannot bypass cycle detection. A target created in this transaction cannot
    # already participate in a path, so that path only needs endpoint locks.
    lock_filter = (
        Question.id.in_([source_question_id, target_question_id])
        if new_target
        else Question.subject_id == subject_id
    )
    locked_questions = await db.scalars(
        select(Question)
        .where(
            lock_filter,
            Question.deleted_at.is_(None),
        )
        .order_by(Question.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    locked_by_id = {question.id: question for question in locked_questions}
    if source_question_id not in locked_by_id or target_question_id not in locked_by_id:
        raise Unprocessable("Question relation endpoints must share a subject")
    questions = [locked_by_id[source_question_id], locked_by_id[target_question_id]]
    if any(not is_question_visible(question, actor) for question in questions):
        raise NotFound("Question not found")
    duplicate = await db.scalar(
        select(QuestionRelation.id).where(
            QuestionRelation.source_question_id == source_question_id,
            QuestionRelation.target_question_id == target_question_id,
            QuestionRelation.relation_type
            == QuestionRelationType.DECOMPOSED_FROM.value,
        )
    )
    if duplicate is not None:
        raise Conflict("Question relation already exists")
    if not new_target:
        edge_result = await db.execute(
            select(
                QuestionRelation.source_question_id,
                QuestionRelation.target_question_id,
            ).where(
                QuestionRelation.relation_type
                == QuestionRelationType.DECOMPOSED_FROM.value
            )
        )
        adjacency: dict[int, set[int]] = {}
        for source_id, target_id in edge_result.all():
            adjacency.setdefault(source_id, set()).add(target_id)
        pending = [target_question_id]
        visited: set[int] = set()
        while pending:
            current = pending.pop()
            if current == source_question_id:
                raise Invalid("Question relation would create a directed cycle")
            if current not in visited:
                visited.add(current)
                pending.extend(adjacency.get(current, set()))
    relation = QuestionRelation(
        source_question_id=source_question_id,
        target_question_id=target_question_id,
        relation_type=QuestionRelationType.DECOMPOSED_FROM.value,
        created_by=actor.id,
    )
    db.add(relation)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(relation)
    return relation


async def delete_question_relation(
    db: AsyncSession,
    *,
    source_question_id: int,
    target_question_id: int,
    actor: User,
    commit: bool = True,
) -> None:
    result = await db.execute(
        select(Question).where(
            Question.id.in_([source_question_id, target_question_id]),
            Question.deleted_at.is_(None),
        )
    )
    questions = {question.id: question for question in result.scalars().all()}
    if source_question_id not in questions or target_question_id not in questions:
        raise NotFound("Question not found")
    source = questions[source_question_id]
    target = questions[target_question_id]
    if not permissions.can(actor, Permission.EDIT_QUESTION, subject_id=source.subject_id):
        raise Forbidden("The user doesn't have enough privileges")
    if not is_question_visible(source, actor) or not is_question_visible(target, actor):
        raise NotFound("Question not found")

    relation = await db.scalar(
        select(QuestionRelation).where(
            QuestionRelation.source_question_id == source_question_id,
            QuestionRelation.target_question_id == target_question_id,
            QuestionRelation.relation_type
            == QuestionRelationType.DECOMPOSED_FROM.value,
        )
    )
    if relation is None:
        raise NotFound("Question relation not found")
    await db.delete(relation)
    await db.flush()
    if commit:
        await db.commit()


async def get_question_relations(
    db: AsyncSession,
    *,
    question_id: int,
    actor: User,
) -> QuestionRelationsRead:
    question = await db.scalar(
        select(Question).where(
            Question.id == question_id,
            Question.deleted_at.is_(None),
        )
    )
    if question is None or not is_question_visible(question, actor):
        raise NotFound("Question not found")

    result = await db.scalars(
        select(QuestionRelation)
        .options(
            selectinload(QuestionRelation.source_question).selectinload(
                Question.knowledge_points
            ),
            selectinload(QuestionRelation.target_question).selectinload(
                Question.knowledge_points
            ),
        )
        .where(
            QuestionRelation.relation_type
            == QuestionRelationType.DECOMPOSED_FROM.value,
            or_(
                QuestionRelation.source_question_id == question_id,
                QuestionRelation.target_question_id == question_id,
            ),
        )
        .order_by(QuestionRelation.id)
    )

    sources: List[QuestionRelationPeerRead] = []
    targets: List[QuestionRelationPeerRead] = []
    for relation in result.unique().all():
        is_source = relation.source_question_id == question_id
        peer = relation.target_question if is_source else relation.source_question
        if (
            peer is None
            or peer.deleted_at is not None
            or not is_question_visible(peer, actor)
        ):
            continue
        item = QuestionRelationPeerRead(
            relation_id=relation.id,
            relation_type=relation.relation_type,
            question=QuestionRelationQuestionRead.model_validate(peer),
            created_at=relation.created_at,
            created_by=relation.created_by,
        )
        (targets if is_source else sources).append(item)

    return QuestionRelationsRead(
        question_id=question_id,
        sources=sources,
        targets=targets,
    )