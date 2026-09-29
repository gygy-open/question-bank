import json
import uuid

import pytest
from pydantic import ValidationError

from app.capabilities.errors import Invalid
from app.models.composition import Composition, CompositionNodeKind, NODE_TYPE_QUESTION, ScopeType
from app.models.question import Question, QuestionType
from app.models.subject import Subject
from app.models.user import User
from app.schemas.composition import CompositionNodeInput
from app.services.composition_service import replace_nodes, sync_question_nodes
from app.services.exporting.composition_assemble import CompositionAssembler
from app.services.exporting.richdoc.latex import rich_doc_to_latex
from app.services.paper_import_service import _resolve_outline_nodes


def _doc(*inline: dict) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": list(inline)}]}


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _blank(blank_id: str) -> dict:
    return {"type": "blank", "attrs": {"blankId": blank_id}}


OPTIONS = [
    {"id": f"opt_{label.lower()}", "label": label, "content": _doc(_text(label))}
    for label in "ABC"
]


def _answer(*slot_ids: str) -> dict:
    return {
        "kind": "option_matching",
        "slots": [{"id": sid, "correct": f"opt_{'abc'[i]}"} for i, sid in enumerate(slot_ids)],
        "allow_reuse": False,
    }


async def _seed(db_session):
    actor = User(username="alice", full_name="Alice", hashed_password="x")
    subject = Subject(name="\u82f1\u8bed", slug="english")
    db_session.add_all([actor, subject])
    await db_session.flush()
    matching = Question(
        subject_id=subject.id,
        q_type=QuestionType.OPTION_MATCHING,
        content=json.dumps(_doc(_text("A"), _blank("b1"), _text("B"), _blank("b2"))),
        options=OPTIONS,
        answer=json.dumps(_answer("b1", "b2")),
        created_by=actor.id,
    )
    single = Question(
        subject_id=subject.id,
        q_type=QuestionType.FREE_RESPONSE,
        content=json.dumps(_doc(_text("\u89e3\u7b54"))),
        created_by=actor.id,
    )
    composition = Composition(
        title="选项匹配", scope_type=ScopeType.SHARED, subject_id=subject.id, created_by=actor.id,
    )
    db_session.add_all([matching, single, composition])
    await db_session.commit()
    return actor, composition, matching, single


def _question(question_id: int, props=None, node_id=None) -> CompositionNodeInput:
    return CompositionNodeInput(
        id=node_id or str(uuid.uuid4()),
        node_kind=CompositionNodeKind.BLOCK,
        node_type=NODE_TYPE_QUESTION,
        question_id=question_id,
        props=props,
    )


async def _replace(db_session, composition, actor, items, expected_revision=None):
    return await replace_nodes(
        db_session,
        comp=composition,
        actor=actor,
        expected_revision=expected_revision or composition.revision,
        batch_id=None,
        items=items,
    )


@pytest.mark.asyncio
async def test_slots_saved_on_option_matching_question(db_session):
    actor, composition, matching, _ = await _seed(db_session)
    props = {"slots": {"b1": {"number": "36", "score": 2}, "b2": {"number": "37"}}}
    _, nodes = await _replace(db_session, composition, actor, [_question(matching.id, props)])
    assert nodes[0].props == props


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("which", "props", "message"),
    [
        ("matching", {"number": "1"}, "use props.slots"),
        ("matching", {"score": 5}, "use props.slots"),
        ("matching", {"slots": {"zz": {"number": "1"}}}, "unknown slot ids"),
        ("single", {"slots": {"b1": {"number": "1"}}}, "only valid on option_matching"),
    ],
)
async def test_props_must_match_frozen_question_type(db_session, which, props, message):
    actor, composition, matching, single = await _seed(db_session)
    question = matching if which == "matching" else single
    with pytest.raises(Invalid, match=message):
        await _replace(db_session, composition, actor, [_question(question.id, props)])


def test_slot_values_are_shape_checked():
    with pytest.raises(ValidationError, match="slots values"):
        _question(1, {"slots": {"b1": {"number": "1", "extra": True}}})
    with pytest.raises(ValidationError, match="score must be between"):
        _question(1, {"slots": {"b1": {"score": -1}}})


@pytest.mark.asyncio
async def test_sync_drops_slots_that_no_longer_exist(db_session):
    actor, composition, matching, _ = await _seed(db_session)
    node_id = str(uuid.uuid4())
    revision, _ = await _replace(
        db_session, composition, actor,
        [_question(matching.id, {"slots": {"b1": {"number": "1"}, "b2": {"number": "2"}}}, node_id)],
    )
    matching.content = json.dumps(_doc(_text("A"), _blank("b1")))
    matching.answer = json.dumps(_answer("b1"))
    matching.content_revision = 2
    await db_session.commit()

    _, nodes = await sync_question_nodes(
        db_session, comp=composition, actor=actor, expected_revision=revision, node_ids=[node_id],
    )
    assert nodes[0].props == {"slots": {"b1": {"number": "1"}}}


def _snapshot(props: dict, *, numbering: bool = True, scoring: bool = True) -> dict:
    question = {
        "id": 5,
        "q_type": "option_matching",
        "content": _doc(_text("A"), _blank("b1"), _text("B"), _blank("b2")),
        "options": OPTIONS,
        "answer": _answer("b1", "b2"),
        "thinking": None, "analysis": None, "summary": None,
    }
    return {
        "schema_version": 3,
        "title": "t",
        "numbering_enabled": numbering,
        "scoring_enabled": scoring,
        "question_display": {"answer": True, "thinking": False, "analysis": False, "summary": False},
        "nodes": [
            {
                "id": "q", "parent_id": None, "position": 0, "node_kind": "block",
                "node_type": "question", "question_id": 5, "question": question, "props": props,
            },
            {
                "id": "m", "parent_id": None, "position": 1, "node_kind": "module",
                "node_type": "question_details",
                "props": {"scope": "all", "fields": {"answer": True, "thinking": False, "analysis": False, "summary": False}},
            },
            {
                "id": "ai", "parent_id": "m", "position": 0, "node_kind": "reference",
                "node_type": "answer_item", "source_question_node_id": "q",
                "props": {"included": True, "overrides": {"answer": None, "thinking": None, "analysis": None, "summary": None}},
            },
        ],
    }


def _blank_labels(stem: dict) -> list:
    return [
        (node.get("attrs") or {}).get("label")
        for node in stem["content"][0]["content"]
        if node["type"] == "blank"
    ]


def test_export_numbers_blanks_and_answer_key_per_slot():
    doc = CompositionAssembler().assemble(
        _snapshot({"slots": {"b1": {"number": "36", "score": 2}, "b2": {"number": "37", "score": 2}}})
    )
    question, details = doc.nodes
    assert question.number == ""
    assert question.score_text == "\u6bcf\u7a7a 2 \u5206"
    assert _blank_labels(question.stem) == ["36", "37"]
    assert [slot["number"] for slot in question.answer["slots"]] == ["36", "37"]
    entry = details.children[0]
    assert entry.number == ""
    assert [slot["number"] for slot in entry.answer["slots"]] == ["36", "37"]


def test_export_uneven_scores_show_total_and_numbering_off_hides_labels():
    doc = CompositionAssembler().assemble(
        _snapshot({"slots": {"b1": {"number": "1", "score": 2}, "b2": {"score": 3}}}, numbering=False)
    )
    question = doc.nodes[0]
    assert question.score_text == "\u5171 5 \u5206"
    assert _blank_labels(question.stem) == [None, None]


def test_latex_renders_blank_label():
    tex = rich_doc_to_latex(_doc({"type": "blank", "attrs": {"blankId": "b1", "label": "36"}}))
    assert tex == "\\underline{\\makebox[4em]{36}}"


def test_docx_renders_slot_numbers_scores_and_answer_key():
    from docx import Document

    from app.services.exporting.renderers.composition_docx import CompositionDocxRenderer

    doc = CompositionAssembler().assemble(
        _snapshot({"slots": {"b1": {"number": "36", "score": 2}, "b2": {"number": "37", "score": 2}}})
    )
    text = "\n".join(p.text for p in Document(CompositionDocxRenderer().render(doc)).paragraphs)
    assert "\uff08\u6bcf\u7a7a 2 \u5206\uff09" in text
    assert "36" in text and "37" in text
    assert "36. A\uff1b37. B" in text


def test_paper_import_numbers_each_slot():
    specs = _resolve_outline_nodes(
        [
            {"kind": "question_ref", "temp_id": "q1", "number": "35"},
            {"kind": "question_ref", "temp_id": "q2", "number": "36", "score": 10},
            {"kind": "question_ref", "temp_id": "q3", "number": "41"},
        ],
        {"q1": 1, "q2": 2, "q3": 3},
        {},
        renumber=True,
        slot_ids_by_question={2: ["b1", "b2", "b3"]},
    )
    assert specs[0] == {"type": "question", "question_id": 1, "number": "1"}
    assert specs[1] == {
        "type": "question",
        "question_id": 2,
        "slots": {"b1": {"number": "2"}, "b2": {"number": "3"}, "b3": {"number": "4"}},
    }
    assert specs[2]["number"] == "5"
