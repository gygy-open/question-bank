"""AI 意图节点 → 组稿 AST 的翻译。

重点在三条:节点 id/kind/slot 由系统生成、Markdown 正文按顶层块拆成单块 rich_text、
question_details 只发模块本身。
"""
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.composition import CompositionNodeInput
from app.services.composition_authoring import AuthoringError, build_nodes


def _types(nodes):
    return [n.node_type for n in nodes]


# --------------------------------------------------------------------------- #
# 系统拥有的字段
# --------------------------------------------------------------------------- #
def test_ids_are_server_generated_uuids():
    nodes = build_nodes([{"type": "page_break"}, {"type": "page_break"}])
    ids = [n.id for n in nodes]
    assert len(set(ids)) == 2
    for nid in ids:
        uuid.UUID(nid)  # 非法 UUID 会抛


def test_node_kind_and_slot_are_derived():
    nodes = build_nodes([
        {"type": "heading", "text": "一、选择题"},
        {"type": "question_details"},
    ])
    heading, details = nodes
    assert heading.node_kind.value == "block"
    assert details.node_kind.value == "module"
    # 根节点不能带 slot。
    assert heading.slot is None and details.slot is None


def test_question_content_is_left_to_the_server():
    """question 的内容是冻结快照,AI 编不得。"""
    (node,) = build_nodes([{"type": "question", "question_id": 7}])
    assert node.content is None
    assert node.question_id == 7


def test_question_group_children_are_left_to_the_server():
    (node,) = build_nodes([{"type": "question_group", "question_group_id": 9}])
    assert node.node_kind.value == "module"
    assert node.question_group_id == 9
    assert node.content is None


# --------------------------------------------------------------------------- #
# Markdown 正文
# --------------------------------------------------------------------------- #
def test_multi_paragraph_markdown_splits_into_single_block_nodes():
    """画布加载多块节点时本就会拆行重新发号,直接按最终形态写入。"""
    nodes = build_nodes([{"type": "rich_text", "markdown": "第一段\n\n第二段"}])
    assert _types(nodes) == ["rich_text", "rich_text"]
    for n in nodes:
        assert n.schema_version == 2
        assert len(n.content["content"]) == 1
    assert {n.id for n in nodes}.__len__() == 2


def test_markdown_formula_and_table_survive():
    nodes = build_nodes([{"type": "rich_text", "markdown": "$$x^2$$"}])
    assert nodes[0].content["content"][0]["type"] == "blockMath"

    nodes = build_nodes([{"type": "rich_text", "markdown": "| a | b |\n| - | - |\n| 1 | 2 |"}])
    assert nodes[0].content["content"][0]["type"] == "table"


def test_empty_markdown_is_rejected_not_silently_dropped():
    """空 rich_text 不是合法节点;静默丢弃会让模型以为写成功了。"""
    with pytest.raises(AuthoringError, match="non-empty markdown"):
        build_nodes([{"type": "rich_text", "markdown": "   "}])


def test_heading_does_not_go_through_markdown():
    """转换器会把 '# x' 降级成 paragraph,所以标题必须走独立构造。"""
    (node,) = build_nodes([{"type": "heading", "text": "# 不该被当作标题语法", "level": 3}])
    assert node.props == {"level": 3}
    blocks = node.content["content"]
    assert len(blocks) == 1 and blocks[0]["type"] == "paragraph"
    assert blocks[0]["content"][0]["text"] == "# 不该被当作标题语法"


def test_heading_defaults_to_level_2():
    (node,) = build_nodes([{"type": "heading", "text": "二、解答题"}])
    assert node.props == {"level": 2}


# --------------------------------------------------------------------------- #
# question_details
# --------------------------------------------------------------------------- #
def test_details_module_emits_no_answer_items():
    """answer_item 由 replace_nodes 按 scope 派生,AI 发了反而会打架。"""
    nodes = build_nodes([{"type": "question_details", "details_fields": {"answer": True}}])
    assert _types(nodes) == ["question_details"]
    assert nodes[0].props["scope"] == "all"
    # 契约要求四个 key 齐全。
    assert set(nodes[0].props["fields"]) == {"answer", "thinking", "analysis", "summary"}
    assert nodes[0].props["fields"] == {
        "answer": True, "thinking": False, "analysis": False, "summary": False
    }


def test_details_rejects_unknown_field_keys():
    with pytest.raises(AuthoringError, match="details_fields keys"):
        build_nodes([{"type": "question_details", "details_fields": {"nope": True}}])


# --------------------------------------------------------------------------- #
# 错误反馈(要能直接回喂给模型)
# --------------------------------------------------------------------------- #
def test_unknown_node_type_lists_the_valid_ones():
    with pytest.raises(AuthoringError, match="must be one of"):
        build_nodes([{"type": "table_of_contents"}])


def test_question_without_id_is_rejected():
    with pytest.raises(AuthoringError, match="requires question_id"):
        build_nodes([{"type": "question"}])


def test_question_show_rejects_unknown_keys():
    with pytest.raises(AuthoringError, match="show keys"):
        build_nodes([{"type": "question", "question_id": 1, "show": {"bogus": True}}])


# --------------------------------------------------------------------------- #
# 产出必须能过契约校验
# --------------------------------------------------------------------------- #
def test_output_satisfies_the_ast_contract():
    nodes = build_nodes([
        {"type": "heading", "text": "一、选择题", "level": 2},
        {"type": "rich_text", "markdown": "先看这道例题。\n\n注意定义域。"},
        {"type": "question", "question_id": 1, "score": 5, "show": {"analysis": True}},
        {"type": "answer_space", "lines": 6, "style": "blank"},
        {"type": "page_break"},
        {"type": "question_details", "details_scope": "all"},
    ])
    assert _types(nodes) == [
        "heading", "rich_text", "rich_text", "question",
        "answer_space", "page_break", "question_details",
    ]
    # 逐节点重新过一遍 pydantic:build_nodes 已经构造过,这里防止将来绕过校验。
    for n in nodes:
        CompositionNodeInput.model_validate(n.model_dump())


def test_answer_space_defaults_are_valid():
    (node,) = build_nodes([{"type": "answer_space"}])
    assert node.props == {"lines": 4, "style": "lined"}


def test_invalid_answer_space_style_is_rejected_by_the_contract():
    with pytest.raises(ValidationError):
        build_nodes([{"type": "answer_space", "style": "dotted"}])
