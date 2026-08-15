from app.crud.crud_question import question as crud_question
from app.models.knowledge_point import KnowledgePoint
from app.models.question import QuestionType
from app.models.subject import Subject
from app.models.tag import Tag
from app.schemas.question import QuestionCreate


async def _seed_taxonomy(db_session):
    subject = Subject(name="数学", slug="math")
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)

    tag = Tag(name="重点", category="feature", subject_id=subject.id)
    kp = KnowledgePoint(name="函数", slug="function", subject_id=subject.id)
    db_session.add_all([tag, kp])
    await db_session.commit()
    await db_session.refresh(tag)
    await db_session.refresh(kp)
    return subject, tag, kp


async def test_create_links_tags_and_knowledge_points(db_session):
    subject, tag, kp = await _seed_taxonomy(db_session)

    created = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content="题干",
            q_type=QuestionType.SINGLE_CHOICE,
            subject_id=subject.id,
            tag_ids=[tag.id],
            knowledge_point_ids=[kp.id],
        ),
    )

    assert [t.id for t in created.tags] == [tag.id]
    assert [k.id for k in created.knowledge_points] == [kp.id]


async def test_get_excludes_soft_deleted(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(content="待删除", q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id),
    )

    await crud_question.remove(db_session, id=created.id)

    assert await crud_question.get(db_session, created.id) is None


async def test_soft_delete_cascades_to_children(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    parent = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(content="父题", q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id),
    )
    child = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content="子题", q_type=QuestionType.SINGLE_CHOICE, subject_id=subject.id, parent_id=parent.id
        ),
    )

    # Drop the identity map so remove() reloads children like a fresh request would.
    db_session.expunge_all()
    await crud_question.remove(db_session, id=parent.id)

    assert await crud_question.get(db_session, child.id) is None


async def test_restore_makes_question_visible_again(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(content="恢复我", q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id),
    )
    await crud_question.remove(db_session, id=created.id)

    await crud_question.restore(db_session, id=created.id)

    assert await crud_question.get(db_session, created.id) is not None


async def test_filters_by_type_difficulty_and_keyword(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content="牛顿第二定律", q_type=QuestionType.SINGLE_CHOICE, difficulty=3, subject_id=subject.id
        ),
    )
    await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content="简答题", q_type=QuestionType.FREE_RESPONSE, difficulty=1, subject_id=subject.id
        ),
    )

    by_type = await crud_question.get_multi_with_filters(db_session, q_type="single_choice")
    assert [q.content for q in by_type] == ["牛顿第二定律"]

    by_keyword = await crud_question.get_multi_with_filters(db_session, keyword="牛顿")
    assert [q.content for q in by_keyword] == ["牛顿第二定律"]

    assert await crud_question.count_with_filters(db_session, difficulty=1) == 1


async def test_tag_filter_matches_only_tagged_questions(db_session):
    subject, tag, _ = await _seed_taxonomy(db_session)
    await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content="带标签", q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id, tag_ids=[tag.id]
        ),
    )
    await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(content="无标签", q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id),
    )

    tagged = await crud_question.get_multi_with_filters(db_session, tag_ids=[tag.id])

    assert [q.content for q in tagged] == ["带标签"]
