"""CompositionAssembler 单测:snapshot v2 → CompositionExportDoc(不涉及渲染格式)。"""

import pytest

from app.services.exporting.composition_assemble import (
    CompositionAssembler,
    CompositionExportError,
)
from app.services.exporting.composition_contracts import (
    ExportAnswerEntry,
    ExportHeadingNode,
    ExportPageBreakNode,
    ExportQuestionDetailsNode,
    ExportQuestionNode,
    ExportRichTextNode,
)


def _rich_doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}


def _wide_doc() -> dict:
    return {"type": "doc", "content": [{"type": "image", "attrs": {"src": "/static/media/a.png"}}]}


def _qsnap(qid: int, **overrides) -> dict:
    base = {
        "id": qid,
        "content_revision": 1,
        "content_schema_version": 2,
        "q_type": "single_choice",
        "content": _rich_doc(f"Q{qid}"),
        "options": [
            {"id": "opt_a", "label": "A", "content": _rich_doc("A")},
            {"id": "opt_b", "label": "B", "content": _rich_doc("B")},
        ],
        "answer": {"kind": "single_choice", "correct": "opt_a"},
        "thinking": _rich_doc(f"思路{qid}"),
        "analysis": _rich_doc(f"解析{qid}"),
        "summary": _rich_doc(f"小结{qid}"),
        "difficulty": 3,
        "source": "seed",
    }
    base.update(overrides)
    return base


def _question_node(nid: str, position: int, qid: int, props: dict | None = None, **qsnap_overrides) -> dict:
    return {
        "id": nid, "parent_id": None, "slot": None, "position": position,
        "node_kind": "block", "node_type": "question", "schema_version": 1,
        "question_id": qid, "question_revision": 1,
        "question": _qsnap(qid, **qsnap_overrides),
        "props": props,
    }


def _heading_node(nid: str, position: int, level: int = 2, parent_id: str | None = None) -> dict:
    return {
        "id": nid, "parent_id": parent_id, "slot": "body" if parent_id else None, "position": position,
        "node_kind": "block", "node_type": "heading", "schema_version": 1,
        "content": _rich_doc("标题"), "props": {"level": level},
    }


def _rich_text_node(nid: str, position: int, parent_id: str | None = None) -> dict:
    return {
        "id": nid, "parent_id": parent_id, "slot": "body" if parent_id else None, "position": position,
        "node_kind": "block", "node_type": "rich_text", "schema_version": 1,
        "content": _rich_doc("正文"),
    }


def _page_break_node(nid: str, position: int) -> dict:
    return {
        "id": nid, "parent_id": None, "slot": None, "position": position,
        "node_kind": "block", "node_type": "page_break", "schema_version": 1,
    }


def _module_node(nid: str, position: int, scope: str = "all", fields: dict | None = None) -> dict:
    complete_fields = {"answer": True, "thinking": False, "analysis": False, "summary": False, **(fields or {})}
    return {
        "id": nid, "parent_id": None, "slot": None, "position": position,
        "node_kind": "module", "node_type": "question_details", "schema_version": 1,
        "props": {"scope": scope, "fields": complete_fields},
    }


def _answer_item_node(
    nid: str, parent_id: str, position: int, source_id: str,
    included: bool = True, overrides: dict | None = None,
) -> dict:
    complete_overrides = {"answer": None, "thinking": None, "analysis": None, "summary": None, **(overrides or {})}
    return {
        "id": nid, "parent_id": parent_id, "slot": "body", "position": position,
        "node_kind": "reference", "node_type": "answer_item", "schema_version": 1,
        "source_question_node_id": source_id, "props": {"included": included, "overrides": complete_overrides},
    }


def _snapshot(nodes: list[dict], **overrides) -> dict:
    base = {
        "schema_version": 2,
        "composition_id": 1,
        "source_revision": 1,
        "title": "稿件",
        "subject_id": 1,
        "finalized_at": "2026-01-01T00:00:00",
        "numbering_enabled": False,
        "scoring_enabled": False,
        "question_display": {"answer": False, "thinking": False, "analysis": False, "summary": False},
        "nodes": nodes,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# 基础节点类型 dispatch
# --------------------------------------------------------------------------- #
def test_assemble_basic_node_types_in_order():
    snap = _snapshot([
        _heading_node("h1", 0),
        _rich_text_node("r1", 1),
        _question_node("q1", 2, qid=1),
        _page_break_node("p1", 3),
    ])
    doc = CompositionAssembler().assemble(snap)
    assert [type(n) for n in doc.nodes] == [
        ExportHeadingNode, ExportRichTextNode, ExportQuestionNode, ExportPageBreakNode,
    ]
    assert doc.nodes[0].level == 2


def test_unsupported_node_type_raises_with_node_id():
    snap = _snapshot([
        {"id": "x1", "parent_id": None, "slot": None, "position": 0, "node_kind": "block", "node_type": "weird"},
    ])
    with pytest.raises(CompositionExportError) as exc:
        CompositionAssembler().assemble(snap)
    assert exc.value.node_id == "x1"
    assert exc.value.node_type == "weird"


def test_unsupported_schema_version_rejected():
    snap = _snapshot([], schema_version=1)
    with pytest.raises(CompositionExportError):
        CompositionAssembler().assemble(snap)


# --------------------------------------------------------------------------- #
# 题号 / 赋分开关
# --------------------------------------------------------------------------- #
def test_number_and_score_hidden_when_switches_off():
    snap = _snapshot([_question_node("q1", 0, qid=1, props={"number": "1", "score": 5})])
    node = CompositionAssembler().assemble(snap).nodes[0]
    assert node.number == ""
    assert node.score is None


def test_number_and_score_shown_when_switches_on():
    snap = _snapshot(
        [_question_node("q1", 0, qid=1, props={"number": "1.2", "score": 4.5})],
        numbering_enabled=True, scoring_enabled=True,
    )
    node = CompositionAssembler().assemble(snap).nodes[0]
    assert node.number == "1.2"
    assert node.score == 4.5


# --------------------------------------------------------------------------- #
# 题目级 show 覆盖 / question_display 全局默认
# --------------------------------------------------------------------------- #
def test_question_field_explicit_override_wins_over_global_default():
    snap = _snapshot(
        [_question_node("q1", 0, qid=1, props={"show": {"answer": False}})],
        question_display={"answer": True, "thinking": False, "analysis": False, "summary": False},
    )
    node = CompositionAssembler().assemble(snap).nodes[0]
    assert node.answer is None


def test_question_field_inherits_global_default_when_not_overridden():
    snap = _snapshot(
        [_question_node("q1", 0, qid=1)],
        question_display={"answer": True, "thinking": False, "analysis": True, "summary": False},
    )
    node = CompositionAssembler().assemble(snap).nodes[0]
    assert node.answer is not None
    assert node.thinking is None
    assert node.analysis is not None
    assert node.summary is None


# --------------------------------------------------------------------------- #
# 选项排版列数
# --------------------------------------------------------------------------- #
def test_option_layout_manual_fixed_columns():
    snap = _snapshot([_question_node("q1", 0, qid=1, props={"optionLayout": 4})])
    node = CompositionAssembler().assemble(snap).nodes[0]
    assert node.option_columns == 2  # 只有 2 个选项，收窄到 2


def test_option_layout_auto_wide_content_forces_single_column():
    snap = _snapshot([
        _question_node(
            "q1", 0, qid=1,
            props={"optionLayout": "auto"},
            options=[
                {"id": "opt_a", "label": "A", "content": _wide_doc()},
                {"id": "opt_b", "label": "B", "content": _rich_doc("B")},
            ],
        )
    ])
    node = CompositionAssembler().assemble(snap).nodes[0]
    assert node.option_columns == 1


# --------------------------------------------------------------------------- #
# question_details 模块:before/all、全局字段、题目级 override、included 排除
# --------------------------------------------------------------------------- #
def test_question_details_children_ordering_and_types():
    snap = _snapshot([
        _question_node("q1", 0, qid=1),
        _module_node("m1", 1, scope="all", fields={"answer": True}),
        _heading_node("ch", 0, level=3, parent_id="m1"),
        _answer_item_node("ai1", "m1", 1, source_id="q1"),
    ])
    doc = CompositionAssembler().assemble(snap)
    module = next(n for n in doc.nodes if isinstance(n, ExportQuestionDetailsNode))
    assert module.scope == "all"
    assert [type(c) for c in module.children] == [ExportHeadingNode, ExportAnswerEntry]


def test_answer_item_override_wins_over_module_global_field():
    snap = _snapshot([
        _question_node("q1", 0, qid=1),
        _module_node("m1", 1, fields={"answer": True, "thinking": False}),
        _answer_item_node("ai1", "m1", 0, source_id="q1", overrides={"answer": False, "thinking": True}),
    ])
    doc = CompositionAssembler().assemble(snap)
    module = next(n for n in doc.nodes if isinstance(n, ExportQuestionDetailsNode))
    entry = module.children[0]
    assert isinstance(entry, ExportAnswerEntry)
    assert entry.answer is None
    assert entry.thinking is not None


def test_answer_item_number_from_source_question_when_numbering_enabled():
    snap = _snapshot([
        _question_node("q1", 0, qid=1, props={"number": "1"}),
        _module_node("m1", 1),
        _answer_item_node("ai1", "m1", 0, source_id="q1"),
    ], numbering_enabled=True)
    doc = CompositionAssembler().assemble(snap)
    module = next(n for n in doc.nodes if isinstance(n, ExportQuestionDetailsNode))
    entry = module.children[0]
    assert isinstance(entry, ExportAnswerEntry)
    assert entry.number == "1"


def test_answer_item_number_empty_when_numbering_disabled():
    snap = _snapshot([
        _question_node("q1", 0, qid=1, props={"number": "1"}),
        _module_node("m1", 1),
        _answer_item_node("ai1", "m1", 0, source_id="q1"),
    ], numbering_enabled=False)
    doc = CompositionAssembler().assemble(snap)
    module = next(n for n in doc.nodes if isinstance(n, ExportQuestionDetailsNode))
    entry = module.children[0]
    assert isinstance(entry, ExportAnswerEntry)
    assert entry.number == ""


def test_answer_item_excluded_when_not_included():
    snap = _snapshot([
        _question_node("q1", 0, qid=1),
        _module_node("m1", 1),
        _answer_item_node("ai1", "m1", 0, source_id="q1", included=False),
    ])
    doc = CompositionAssembler().assemble(snap)
    module = next(n for n in doc.nodes if isinstance(n, ExportQuestionDetailsNode))
    assert module.children == []


def test_answer_item_missing_source_question_raises():
    snap = _snapshot([
        _module_node("m1", 0),
        _answer_item_node("ai1", "m1", 0, source_id="missing"),
    ])
    with pytest.raises(CompositionExportError) as exc:
        CompositionAssembler().assemble(snap)
    assert exc.value.node_id == "ai1"


def test_same_question_referenced_twice_produces_independent_nodes():
    snap = _snapshot([
        _question_node("q1", 0, qid=1),
        _question_node("q2", 1, qid=1),
    ])
    doc = CompositionAssembler().assemble(snap)
    assert doc.nodes[0].stem == doc.nodes[1].stem
    assert doc.nodes[0] is not doc.nodes[1]
