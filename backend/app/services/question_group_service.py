import json
from datetime import datetime
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Conflict, Forbidden, Invalid, NotFound, Unprocessable
from app.core import permissions
from app.core.permissions import Permission
from app.crud.crud_question_group import question_group as crud_question_group
from app.crud.crud_question_group import stimulus as crud_stimulus
from app.crud.crud_question import is_question_visible
from app.models.question import Question, QuestionVisibility
from app.models.question_group import (
    QuestionGroup,
    QuestionGroupItem,
    QuestionRelation,
    QuestionRelationType,
    Stimulus,
)
from app.models.user import User
from app.schemas.question_group import QuestionGroupItemInput


def _error(code: int, detail: str) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def _assert_private_access(resource: Stimulus | QuestionGroup, actor: User) -> None:
    if (
        resource.visibility == QuestionVisibility.PRIVATE.value
        and not actor.is_superuser
        and resource.created_by != actor.id
    ):
        raise _error(status.HTTP_404_NOT_FOUND, "Resource not found")


async def get_stimulus(db: AsyncSession, stimulus_id: int, actor: User) -> Stimulus:
    stimulus = await crud_stimulus.get_active(db, stimulus_id)
    if stimulus is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Stimulus not found")
    _assert_private_access(stimulus, actor)
    return stimulus


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
    _assert_private_access(stimulus, actor)
    values = {"updated_by": actor.id, "updated_at": datetime.utcnow()}
    if content is not None:
        values["content"] = json.dumps(content, ensure_ascii=False)
    if status_value is not None:
        values["status"] = status_value
    if visibility is not None:
        if visibility == QuestionVisibility.PRIVATE.value:
            public_group = await db.scalar(
                select(QuestionGroup.id).where(
                    QuestionGroup.stimulus_id == stimulus.id,
                    QuestionGroup.deleted_at.is_(None),
                    QuestionGroup.visibility == QuestionVisibility.PUBLIC.value,
                ).limit(1)
            )
            if public_group is not None:
                raise _error(422, "公开题组引用的材料不能设为私有")
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
        .values(**values, revision=Stimulus.revision + 1)
    )
    if result.rowcount == 0:
        raise _error(status.HTTP_409_CONFLICT, "Stimulus revision mismatch")
    await db.commit()
    return await get_stimulus(db, stimulus.id, actor)


async def _validate_group_refs(
    db: AsyncSession,
    *,
    subject_id: int,
    stimulus_id: int,
    items: List[QuestionGroupItemInput],
    visibility: str,
    actor: User,
) -> tuple[Stimulus, List[Question]]:
    stimulus = await get_stimulus(db, stimulus_id, actor)
    if stimulus.subject_id != subject_id:
        raise _error(422, "材料与题组必须属于同一学科")
    ids = [item.question_id for item in items]
    result = await db.execute(
        select(Question).where(Question.id.in_(ids), Question.deleted_at.is_(None))
    )
    questions = list(result.scalars().all())
    if len(questions) != len(ids):
        raise _error(422, "题组包含不存在或已删除的题目")
    if any(question.subject_id != subject_id for question in questions):
        raise _error(422, "材料、题组和题目必须属于同一学科")
    for question in questions:
        if (
            question.visibility == QuestionVisibility.PRIVATE.value
            and not actor.is_superuser
            and question.created_by != actor.id
        ):
            raise _error(status.HTTP_404_NOT_FOUND, "Question not found")
    if visibility == QuestionVisibility.PUBLIC.value and (
        stimulus.visibility == QuestionVisibility.PRIVATE.value
        or any(q.visibility == QuestionVisibility.PRIVATE.value for q in questions)
    ):
        raise _error(422, "公开题组不能引用私有材料或题目")
    return stimulus, questions


async def get_group(db: AsyncSession, group_id: int, actor: User) -> QuestionGroup:
    group = await crud_question_group.get_active(db, group_id)
    if group is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Question group not found")
    _assert_private_access(group, actor)
    return group


async def create_group(
    db: AsyncSession,
    *,
    subject_id: int,
    stimulus_id: int,
    items: List[QuestionGroupItemInput],
    status_value: str,
    visibility: str,
    actor: User,
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> QuestionGroup:
    await _validate_group_refs(
        db,
        subject_id=subject_id,
        stimulus_id=stimulus_id,
        items=items,
        visibility=visibility,
        actor=actor,
    )
    group = QuestionGroup(
        subject_id=subject_id,
        stimulus_id=stimulus_id,
        status=status_value,
        visibility=visibility,
        source=source,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(group)
    await db.flush()
    db.add_all(
        QuestionGroupItem(
            group_id=group.id, question_id=item.question_id, position=item.position
        )
        for item in items
    )
    await db.commit()
    return await get_group(db, group.id, actor)


async def update_group(
    db: AsyncSession,
    *,
    group: QuestionGroup,
    expected_revision: int,
    actor: User,
    stimulus_id: Optional[int] = None,
    items: Optional[List[QuestionGroupItemInput]] = None,
    status_value: Optional[str] = None,
    visibility: Optional[str] = None,
    source: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> QuestionGroup:
    _assert_private_access(group, actor)
    effective_items = items or [
        QuestionGroupItemInput(question_id=item.question_id, position=item.position)
        for item in group.items
    ]
    effective_stimulus_id = stimulus_id or group.stimulus_id
    effective_visibility = visibility or group.visibility
    await _validate_group_refs(
        db,
        subject_id=group.subject_id,
        stimulus_id=effective_stimulus_id,
        items=effective_items,
        visibility=effective_visibility,
        actor=actor,
    )
    values = {
        "stimulus_id": effective_stimulus_id,
        "visibility": effective_visibility,
        "updated_by": actor.id,
        "updated_at": datetime.utcnow(),
    }
    if status_value is not None:
        values["status"] = status_value
    if source is not None:
        values["source"] = source
    if metadata is not None:
        values["metadata_json"] = json.dumps(metadata, ensure_ascii=False)
    result = await db.execute(
        update(QuestionGroup)
        .where(
            QuestionGroup.id == group.id,
            QuestionGroup.revision == expected_revision,
            QuestionGroup.deleted_at.is_(None),
        )
        .values(**values, revision=QuestionGroup.revision + 1)
    )
    if result.rowcount == 0:
        raise _error(status.HTTP_409_CONFLICT, "Question group revision mismatch")
    if items is not None:
        await db.execute(delete(QuestionGroupItem).where(QuestionGroupItem.group_id == group.id))
        db.add_all(
            QuestionGroupItem(
                group_id=group.id, question_id=item.question_id, position=item.position
            )
            for item in items
        )
    await db.commit()
    return await get_group(db, group.id, actor)


async def delete_group(
    db: AsyncSession, *, group: QuestionGroup, expected_revision: int, actor: User
) -> None:
    _assert_private_access(group, actor)
    result = await db.execute(
        update(QuestionGroup)
        .where(
            QuestionGroup.id == group.id,
            QuestionGroup.revision == expected_revision,
            QuestionGroup.deleted_at.is_(None),
        )
        .values(
            deleted_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            updated_by=actor.id,
            revision=QuestionGroup.revision + 1,
        )
    )
    if result.rowcount == 0:
        raise _error(status.HTTP_409_CONFLICT, "Question group revision mismatch")
    await db.execute(delete(QuestionGroupItem).where(QuestionGroupItem.group_id == group.id))
    await db.commit()


async def create_question_relation(
    db: AsyncSession,
    *,
    source_question_id: int,
    target_question_id: int,
    actor: User,
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

    # MySQL serializes all relation writes in one subject on these row locks.
    # SQLite ignores FOR UPDATE, but its single-writer transaction prevents an
    # unchecked concurrent write from committing.
    locked_questions = await db.scalars(
        select(Question)
        .where(
            Question.subject_id == subject_id,
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
    edge_result = await db.execute(
        select(QuestionRelation.source_question_id, QuestionRelation.target_question_id).where(
            QuestionRelation.relation_type == QuestionRelationType.DECOMPOSED_FROM.value
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
    await db.commit()
    await db.refresh(relation)
    return relation