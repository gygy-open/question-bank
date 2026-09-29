import json
import uuid

import pytest

from app.capabilities.errors import Invalid, Unprocessable
from app.models.composition import (
    BODY_SLOT,
    Composition,
    CompositionNodeKind,
    NODE_TYPE_ANSWER_SPACE,
    NODE_TYPE_QUESTION,
    NODE_TYPE_QUESTION_GROUP,
    ScopeType,
)
from app.models.question import Question, QuestionType
from app.models.stimulus import Stimulus
from app.models.subject import Subject
from app.models.user import User
from app.schemas.composition import CompositionNodeInput
from app.services.composition_service import replace_nodes


def _uid() -> str:
    return str(uuid.uuid4())


def _rich_doc(text: str) -> dict:
    return {
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    }


async def _seed(db_session):
    actor = User(username="alice", full_name="Alice", hashed_password="x")
    subject = Subject(name="语文", slug="chinese")
    db_session.add_all([actor, subject])
    await db_session.flush()

    stimulus = Stimulus(
        subject_id=subject.id,
        content=json.dumps(_rich_doc("材料一"), ensure_ascii=False),
        revision=7,
        content_revision=3,
        created_by=actor.id,
    )
    db_session.add(stimulus)
    await db_session.flush()
    questions = [
        Question(
            subject_id=subject.id,
            q_type=QuestionType.FREE_RESPONSE,
            content=json.dumps(_rich_doc(text), ensure_ascii=False),
            content_revision=revision,
            stimulus_id=stimulus.id,
            stimulus_position=position,
            created_by=actor.id,
        )
        for position, (text, revision) in enumerate(
            (("小题一", 2), ("小题二", 4), ("小题三", 1))
        )
    ]
    standalone = Question(
        subject_id=subject.id,
        q_type=QuestionType.FREE_RESPONSE,
        content=json.dumps(_rich_doc("独立题"), ensure_ascii=False),
        created_by=actor.id,
    )
    db_session.add_all([*questions, standalone])
    composition = Composition(
        title="材料题稿",
        scope_type=ScopeType.SHARED,
        subject_id=subject.id,
        created_by=actor.id,
    )
    db_session.add(composition)
    await db_session.commit()
    return actor, composition, stimulus, questions, standalone


def _module(module_id: str, stimulus_id: int) -> CompositionNodeInput:
    return CompositionNodeInput(
        id=module_id,
        node_kind=CompositionNodeKind.MODULE,
        node_type=NODE_TYPE_QUESTION_GROUP,
        stimulus_id=stimulus_id,
    )


def _child(module_id: str, question_id: int, node_id=None, **kwargs) -> CompositionNodeInput:
    return CompositionNodeInput(
        id=node_id or _uid(),
        parent_id=module_id,
        slot=BODY_SLOT,
        node_kind=CompositionNodeKind.BLOCK,
        node_type=NODE_TYPE_QUESTION,
        question_id=question_id,
        **kwargs,
    )


def _questions(nodes):
    return sorted(
        (node for node in nodes if node.node_type == NODE_TYPE_QUESTION and node.parent_id),
        key=lambda node: node.position,
    )


async def _replace(db_session, composition, actor, items):
    return await replace_nodes(
        db_session,
        comp=composition,
        actor=actor,
        expected_revision=composition.revision,
        batch_id=None,
        items=items,
    )


@pytest.mark.asyncio
async def test_new_group_freezes_stimulus_and_orders_subset_by_material(db_session):
    actor, composition, stimulus, questions, _ = await _seed(db_session)
    module_id = _uid()
    revision, nodes = await _replace(
        db_session,
        composition,
        actor,
        [
            _module(module_id, stimulus.id),
            _child(module_id, questions[2].id),
            _child(module_id, questions[0].id),
        ],
    )
    module = next(node for node in nodes if node.node_type == NODE_TYPE_QUESTION_GROUP)
    assert revision == 2
    assert module.content == _rich_doc("材料一")
    assert (module.stimulus_id, module.stimulus_revision) == (stimulus.id, 3)
    frozen = _questions(nodes)
    assert [node.question_id for node in frozen] == [questions[0].id, questions[2].id]
    assert [node.question_revision for node in frozen] == [2, 1]


@pytest.mark.asyncio
async def test_existing_group_keeps_snapshots_allows_subset_edits_but_not_reorder(db_session):
    actor, composition, stimulus, questions, _ = await _seed(db_session)
    module_id = _uid()
    _, nodes = await _replace(
        db_session,
        composition,
        actor,
        [_module(module_id, stimulus.id), *[_child(module_id, q.id) for q in questions[:2]]],
    )
    first, second = _questions(nodes)

    stimulus.content = json.dumps(_rich_doc("材料二"), ensure_ascii=False)
    stimulus.content_revision = 4
    questions[0].content = json.dumps(_rich_doc("已更新小题"), ensure_ascii=False)
    questions[0].content_revision = 3
    await db_session.commit()

    answer_space_id = _uid()
    kept = [
        _module(module_id, stimulus.id),
        _child(module_id, questions[0].id, first.id, props={"score": 8}),
        CompositionNodeInput(
            id=answer_space_id,
            parent_id=module_id,
            slot=BODY_SLOT,
            node_kind=CompositionNodeKind.BLOCK,
            node_type=NODE_TYPE_ANSWER_SPACE,
            source_question_node_id=first.id,
            props={"lines": 4, "style": "lined"},
        ),
        _child(module_id, questions[1].id, second.id),
    ]
    _, nodes = await _replace(db_session, composition, actor, kept)
    module = next(node for node in nodes if node.node_type == NODE_TYPE_QUESTION_GROUP)
    replaced = _questions(nodes)
    assert module.content == _rich_doc("材料一")
    assert module.stimulus_revision == 3
    assert replaced[0].content == first.content
    assert replaced[0].question_revision == 2
    assert replaced[0].props == {"score": 8}
    space = next(node for node in nodes if node.node_type == NODE_TYPE_ANSWER_SPACE)
    assert space.source_question_node_id == first.id

    with pytest.raises(Invalid, match="cannot reorder"):
        await _replace(db_session, composition, actor, [kept[0], kept[3], kept[1], kept[2]])

    _, nodes = await _replace(db_session, composition, actor, [kept[0], kept[3]])
    assert [node.question_id for node in _questions(nodes)] == [questions[1].id]

    readded_id = _uid()
    _, nodes = await _replace(
        db_session,
        composition,
        actor,
        [kept[0], _child(module_id, questions[0].id, readded_id), kept[3]],
    )
    readded = next(node for node in nodes if node.id == readded_id)
    assert readded.question_revision == 3
    assert readded.content["content"] == _rich_doc("已更新小题")


@pytest.mark.asyncio
async def test_group_rejects_foreign_members_duplicates_and_empty_selection(db_session):
    actor, composition, stimulus, questions, standalone = await _seed(db_session)
    module_id = _uid()
    with pytest.raises(Unprocessable, match="does not belong to stimulus"):
        await _replace(
            db_session,
            composition,
            actor,
            [_module(module_id, stimulus.id), _child(module_id, standalone.id)],
        )
    with pytest.raises(Invalid, match="must not repeat"):
        await _replace(
            db_session,
            composition,
            actor,
            [
                _module(module_id, stimulus.id),
                _child(module_id, questions[0].id),
                _child(module_id, questions[0].id),
            ],
        )
    with pytest.raises(Invalid, match="at least one question"):
        await _replace(db_session, composition, actor, [_module(module_id, stimulus.id)])


@pytest.mark.asyncio
async def test_stimulus_bound_question_cannot_be_frozen_as_root_node(db_session):
    actor, composition, _, questions, standalone = await _seed(db_session)
    with pytest.raises(Unprocessable, match="inside a question_group"):
        await _replace(
            db_session,
            composition,
            actor,
            [
                CompositionNodeInput(
                    id=_uid(),
                    node_kind=CompositionNodeKind.BLOCK,
                    node_type=NODE_TYPE_QUESTION,
                    question_id=questions[0].id,
                )
            ],
        )
    revision, _ = await _replace(
        db_session,
        composition,
        actor,
        [
            CompositionNodeInput(
                id=_uid(),
                node_kind=CompositionNodeKind.BLOCK,
                node_type=NODE_TYPE_QUESTION,
                question_id=standalone.id,
            )
        ],
    )
    assert revision == 2
