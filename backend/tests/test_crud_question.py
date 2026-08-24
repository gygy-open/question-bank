import pytest

from app.crud.crud_question import question as crud_question
from app.models.knowledge_point import KnowledgePoint
from app.models.question import QuestionStatus, QuestionType, SCHEMA_VERSION
from app.models.subject import Subject
from app.models.tag import Tag
from app.schemas.question import Question as QuestionSchema
from app.schemas.question import QuestionCreate, QuestionUpdate


def doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _options():
    return [
        {"id": "opt_a", "label": "A", "content": doc("甲")},
        {"id": "opt_b", "label": "B", "content": doc("乙")},
    ]


def _single_choice(content: str = "题干", subject_id=None, **kwargs) -> QuestionCreate:
    return QuestionCreate(
        content=doc(content),
        q_type=QuestionType.SINGLE_CHOICE,
        options=_options(),
        answer={"kind": "single_choice", "correct": "opt_a"},
        subject_id=subject_id,
        **kwargs,
    )


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
        obj_in=_single_choice(subject_id=subject.id, tag_ids=[tag.id], knowledge_point_ids=[kp.id]),
    )

    assert [t.id for t in created.tags] == [tag.id]
    assert [k.id for k in created.knowledge_points] == [kp.id]


# --------------------------------------------------------------------------- #
# v2 JSON 边界:roundtrip + version default
# --------------------------------------------------------------------------- #
async def test_create_stores_json_strings_and_roundtrips(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)

    created = await crud_question.create_with_tags(
        db_session,
        obj_in=_single_choice(subject_id=subject.id),
    )

    # content / answer 落库为 JSON 字符串;options 为原生 JSON 列表。
    assert isinstance(created.content, str)
    assert isinstance(created.answer, str)
    assert isinstance(created.options, list)

    # 版本默认 = SCHEMA_VERSION,needs_review 默认 False。
    assert created.content_schema_version == SCHEMA_VERSION
    assert created.needs_review is False

    # Pydantic 响应模型从 ORM 读取,反序列化回对象。
    schema = QuestionSchema.model_validate(created)
    assert schema.content == doc("题干")
    assert schema.answer.kind == "single_choice"
    assert schema.answer.correct == "opt_a"
    assert [o.id for o in schema.options] == ["opt_a", "opt_b"]


async def test_free_response_roundtrip(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content=doc("简答"),
            q_type=QuestionType.FREE_RESPONSE,
            answer={"kind": "free_response", "reference": doc("参考")},
            subject_id=subject.id,
        ),
    )
    schema = QuestionSchema.model_validate(created)
    assert schema.answer.kind == "free_response"
    assert schema.answer.reference == doc("参考")
    assert schema.options is None


# --------------------------------------------------------------------------- #
# 更新:合并现状后完整校验
# --------------------------------------------------------------------------- #
async def test_update_content_only_preserves_answer(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session, obj_in=_single_choice(subject_id=subject.id)
    )

    updated = await crud_question.update_with_tags(
        db_session, db_obj=created, obj_in=QuestionUpdate(content=doc("新题干"))
    )

    schema = QuestionSchema.model_validate(updated)
    assert schema.content == doc("新题干")
    assert schema.answer.correct == "opt_a"  # 答案保持不变


async def test_update_answer_dangling_option_rejected_after_merge(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session, obj_in=_single_choice(subject_id=subject.id)
    )

    # 只改答案,引用一个不存在的 option id → 合并现有 options 后终检应拒绝。
    with pytest.raises(ValueError):
        await crud_question.update_with_tags(
            db_session,
            db_obj=created,
            obj_in=QuestionUpdate(answer={"kind": "single_choice", "correct": "opt_missing"}),
        )


async def test_status_only_publish_rejects_incomplete_draft(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content=doc("未完成"),
            q_type=QuestionType.FREE_RESPONSE,
            subject_id=subject.id,
        ),
    )

    with pytest.raises(ValueError, match="answer is required"):
        await crud_question.update_with_tags(
            db_session,
            db_obj=created,
            obj_in=QuestionUpdate(status=QuestionStatus.PUBLISHED),
        )


async def test_update_change_type_to_free_response_drops_options(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session, obj_in=_single_choice(subject_id=subject.id)
    )

    updated = await crud_question.update_with_tags(
        db_session,
        db_obj=created,
        obj_in=QuestionUpdate(
            q_type=QuestionType.FREE_RESPONSE,
            answer={"kind": "free_response", "reference": doc("参考")},
        ),
    )

    schema = QuestionSchema.model_validate(updated)
    assert schema.q_type == QuestionType.FREE_RESPONSE
    assert schema.options is None


async def test_get_excludes_soft_deleted(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(content=doc("待删除"), q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id),
    )

    await crud_question.remove(db_session, id=created.id)

    assert await crud_question.get(db_session, created.id) is None


async def test_soft_delete_cascades_to_children(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    parent = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(content=doc("父题"), q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id),
    )
    child = await crud_question.create_with_tags(
        db_session,
        obj_in=_single_choice(content="子题", subject_id=subject.id, parent_id=parent.id),
    )

    # Drop the identity map so remove() reloads children like a fresh request would.
    db_session.expunge_all()
    await crud_question.remove(db_session, id=parent.id)

    assert await crud_question.get(db_session, child.id) is None


async def test_restore_makes_question_visible_again(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    created = await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(content=doc("恢复我"), q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id),
    )
    await crud_question.remove(db_session, id=created.id)

    await crud_question.restore(db_session, id=created.id)

    assert await crud_question.get(db_session, created.id) is not None


async def test_filters_by_type_difficulty_and_keyword(db_session):
    subject, _, _ = await _seed_taxonomy(db_session)
    await crud_question.create_with_tags(
        db_session,
        obj_in=_single_choice(content="牛顿第二定律", subject_id=subject.id, difficulty=3),
    )
    await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content=doc("简答题"), q_type=QuestionType.FREE_RESPONSE, difficulty=1, subject_id=subject.id
        ),
    )

    by_type = await crud_question.get_multi_with_filters(db_session, q_type="single_choice")
    assert len(by_type) == 1

    by_keyword = await crud_question.get_multi_with_filters(db_session, keyword="牛顿")
    assert len(by_keyword) == 1

    assert await crud_question.count_with_filters(db_session, difficulty=1) == 1


async def test_tag_filter_matches_only_tagged_questions(db_session):
    subject, tag, _ = await _seed_taxonomy(db_session)
    await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(
            content=doc("带标签"), q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id, tag_ids=[tag.id]
        ),
    )
    await crud_question.create_with_tags(
        db_session,
        obj_in=QuestionCreate(content=doc("无标签"), q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id),
    )

    tagged = await crud_question.get_multi_with_filters(db_session, tag_ids=[tag.id])

    assert len(tagged) == 1
    assert QuestionSchema.model_validate(tagged[0]).content == doc("带标签")
