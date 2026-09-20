import json
import uuid

import pytest

from app.capabilities.errors import Invalid
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
from app.models.question_group import QuestionGroup, QuestionGroupItem, Stimulus
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


async def _seed_group(db_session):
    actor = User(username="alice", full_name="Alice", hashed_password="x")
    subject = Subject(name="语文", slug="chinese")
    db_session.add_all([actor, subject])
    await db_session.flush()

    stimulus = Stimulus(
        subject_id=subject.id,
        content=json.dumps(_rich_doc("材料一"), ensure_ascii=False),
        revision=3,
        created_by=actor.id,
    )
    questions = [
        Question(
            subject_id=subject.id,
            q_type=QuestionType.FREE_RESPONSE,
            content=json.dumps(_rich_doc(text), ensure_ascii=False),
            content_revision=revision,
            created_by=actor.id,
        )
        for text, revision in (("小题一", 2), ("小题二", 4))
    ]
    db_session.add_all([stimulus, *questions])
    await db_session.flush()

    group = QuestionGroup(
        subject_id=subject.id,
        stimulus_id=stimulus.id,
        revision=5,
        created_by=actor.id,
    )
    db_session.add(group)
    await db_session.flush()
    db_session.add_all(
        QuestionGroupItem(group_id=group.id, question_id=question.id, position=position)
        for position, question in enumerate(questions)
    )
    composition = Composition(
        title="题组稿",
        scope_type=ScopeType.SHARED,
        subject_id=subject.id,
        created_by=actor.id,
    )
    db_session.add(composition)
    await db_session.commit()
    return actor, composition, group, stimulus, questions


@pytest.mark.asyncio
async def test_question_group_replace_freezes_source_and_preserves_member_order(db_session):
    actor, composition, group, stimulus, questions = await _seed_group(db_session)
    module_id = _uid()
    module = CompositionNodeInput(
        id=module_id,
        node_kind=CompositionNodeKind.MODULE,
        node_type=NODE_TYPE_QUESTION_GROUP,
        question_group_id=group.id,
    )

    revision, frozen_nodes = await replace_nodes(
        db_session,
        comp=composition,
        actor=actor,
        expected_revision=1,
        batch_id=None,
        items=[module],
    )
    frozen_module = next(node for node in frozen_nodes if node.node_type == NODE_TYPE_QUESTION_GROUP)
    frozen_questions = [node for node in frozen_nodes if node.node_type == NODE_TYPE_QUESTION]
    assert revision == 2
    assert frozen_module.content == _rich_doc("材料一")
    assert frozen_module.question_group_revision == 5
    assert frozen_module.stimulus_id == stimulus.id
    assert frozen_module.stimulus_revision == 3
    assert [node.question_id for node in frozen_questions] == [q.id for q in questions]
    assert [node.question_revision for node in frozen_questions] == [2, 4]

    stimulus.content = json.dumps(_rich_doc("材料二"), ensure_ascii=False)
    stimulus.revision = 4
    questions[0].content = json.dumps(_rich_doc("已更新小题"), ensure_ascii=False)
    questions[0].content_revision = 3
    group.revision = 6
    await db_session.commit()

    first, second = frozen_questions
    answer_space_id = _uid()
    replacement = [
        module,
        CompositionNodeInput(
            id=first.id,
            parent_id=module_id,
            slot=BODY_SLOT,
            node_kind=CompositionNodeKind.BLOCK,
            node_type=NODE_TYPE_QUESTION,
            question_id=first.question_id,
            props={"score": 8},
        ),
        CompositionNodeInput(
            id=answer_space_id,
            parent_id=module_id,
            slot=BODY_SLOT,
            node_kind=CompositionNodeKind.BLOCK,
            node_type=NODE_TYPE_ANSWER_SPACE,
            source_question_node_id=first.id,
            props={"lines": 4, "style": "lined"},
        ),
        CompositionNodeInput(
            id=second.id,
            parent_id=module_id,
            slot=BODY_SLOT,
            node_kind=CompositionNodeKind.BLOCK,
            node_type=NODE_TYPE_QUESTION,
            question_id=second.question_id,
        ),
    ]
    revision, replaced_nodes = await replace_nodes(
        db_session,
        comp=composition,
        actor=actor,
        expected_revision=revision,
        batch_id=None,
        items=replacement,
    )
    replaced_module = next(
        node for node in replaced_nodes if node.node_type == NODE_TYPE_QUESTION_GROUP
    )
    replaced_questions = [node for node in replaced_nodes if node.node_type == NODE_TYPE_QUESTION]
    answer_space = next(node for node in replaced_nodes if node.node_type == NODE_TYPE_ANSWER_SPACE)
    assert revision == 3
    assert replaced_module.content == _rich_doc("材料一")
    assert replaced_module.question_group_revision == 5
    assert replaced_module.stimulus_revision == 3
    assert replaced_questions[0].content == frozen_questions[0].content
    assert replaced_questions[0].question_revision == 2
    assert replaced_questions[0].props == {"score": 8}
    assert answer_space.source_question_node_id == first.id
    assert answer_space.props == {"lines": 4, "style": "lined"}

    reordered = [replacement[0], replacement[3], replacement[1], replacement[2]]
    with pytest.raises(Invalid, match="cannot change member question order"):
        await replace_nodes(
            db_session,
            comp=composition,
            actor=actor,
            expected_revision=revision,
            batch_id=None,
            items=reordered,
        )
    assert composition.revision == revision