"""组稿增量编辑原语的服务端校验与归一。

原语本身在前端执行,服务端这一趟只做两件事:把 Markdown 转成 RichDoc(转换器只有后端
一份,前端再实现一份必然漂移),以及把模型给的松散入参收敛掉。后者不是洁癖 ——
不合法的入参若被推给前端,要绕一整圈才会以「客户端执行失败」回来。
"""
import json

import pytest

from app.ai import tools as ai_tools
from app.ai.contracts import AgentScene
from app.ai.tools.composition_edit import prepare_edit_composition
from app.services.composition_authoring import AuthoringError
from app.services.composition_ops import MAX_OPERATIONS, prepare_operations


def _one(op: dict) -> dict:
    return prepare_operations([op])[0]


# --------------------------------------------------------------------------- #
# insert_nodes
# --------------------------------------------------------------------------- #
def test_rich_text_markdown_is_converted_server_side():
    """前端拿到的必须是 RichDoc —— 它没有(也不该有)Markdown 解析器。"""
    out = _one({
        "op": "insert_nodes",
        "after": "node-1",
        "nodes": [{"type": "rich_text", "markdown": "第一段\n\n第二段"}],
    })
    node = out["nodes"][0]
    assert "markdown" not in node
    blocks = node["rich_doc_blocks"]
    # 画布每行恰好一个顶层块,所以多段 Markdown 在这里就拆开,而不是等加载时重新发号。
    assert len(blocks) == 2
    assert all(b["type"] == "doc" and len(b["content"]) == 1 for b in blocks)


def test_rich_text_requires_non_empty_markdown():
    """静默跳过会让模型以为写成功了。"""
    with pytest.raises(AuthoringError, match="non-empty markdown"):
        _one({"op": "insert_nodes", "nodes": [{"type": "rich_text", "markdown": "   "}]})


def test_heading_defaults_to_level_2_and_rejects_out_of_range():
    assert _one({
        "op": "insert_nodes",
        "nodes": [{"type": "heading", "text": "一、选择题"}],
    })["nodes"][0] == {"type": "heading", "text": "一、选择题", "level": 2}

    with pytest.raises(AuthoringError, match="level must be in 1..4"):
        _one({"op": "insert_nodes", "nodes": [{"type": "heading", "text": "x", "level": 7}]})


def test_question_node_only_carries_a_reference():
    """content 是冻结快照,只能由前端拿实时题目构造 —— 模型不拥有这个字段。"""
    node = _one({
        "op": "insert_nodes",
        "nodes": [{"type": "question", "question_id": 42, "score": 5, "content": "模型瞎编的"}],
    })["nodes"][0]
    assert node == {"type": "question", "question_id": 42, "score": 5}


def test_question_details_is_not_insertable():
    """它有 answer_item 派生这层惯用法,必须走 add_details_module。"""
    with pytest.raises(AuthoringError, match="type must be one of"):
        _one({"op": "insert_nodes", "nodes": [{"type": "question_details"}]})


def test_insert_anchor_defaults_to_end():
    out = _one({"op": "insert_nodes", "nodes": [{"type": "page_break"}]})
    assert out["after"] == "end"


def test_answer_space_defaults_are_deferred_and_enum_is_checked():
    # 行数/样式缺省时不在 ops 层定下来,留给 authoring 按题型与分值推导。
    assert _one({
        "op": "insert_nodes",
        "nodes": [{"type": "answer_space"}],
    })["nodes"][0] == {"type": "answer_space"}

    assert _one({
        "op": "insert_nodes",
        "nodes": [{"type": "answer_space", "lines": 7, "style": "blank"}],
    })["nodes"][0] == {"type": "answer_space", "lines": 7, "style": "blank"}

    with pytest.raises(AuthoringError, match="style must be one of"):
        _one({"op": "insert_nodes", "nodes": [{"type": "answer_space", "style": "dotted"}]})


# --------------------------------------------------------------------------- #
# 其余原语
# --------------------------------------------------------------------------- #
def test_remove_nodes_requires_ids():
    assert _one({"op": "remove_nodes", "node_ids": ["a", "b"]})["node_ids"] == ["a", "b"]
    with pytest.raises(AuthoringError, match="non-empty array of node ids"):
        _one({"op": "remove_nodes", "node_ids": []})


def test_move_node_without_before_means_move_to_the_end():
    assert _one({"op": "move_node", "node_id": "a"})["before"] is None


def test_set_node_props_whitelists_system_owned_fields():
    """节点 id / 内容 / 软指针 / question_id 的真值不在模型手里,开放就会让稿件和题库对不上。"""
    for forbidden in ("id", "content", "question_id", "source_question_node_id"):
        with pytest.raises(AuthoringError, match="keys must be within"):
            _one({"op": "set_node_props", "node_id": "a", "props": {forbidden: "x"}})


def test_set_node_props_supports_clearing():
    out = _one({"op": "set_node_props", "node_id": "a", "clear": ["score"]})
    assert out["clear"] == ["score"] and out["props"] == {}
    with pytest.raises(AuthoringError, match="at least one property"):
        _one({"op": "set_node_props", "node_id": "a"})


def test_show_question_fields_is_tri_state():
    out = _one({
        "op": "show_question_fields",
        "node_id": "a",
        "show": {"thinking": "show", "analysis": "inherit"},
    })
    assert out["show"] == {"thinking": "show", "analysis": "inherit"}
    with pytest.raises(AuthoringError, match="must be one of"):
        _one({"op": "show_question_fields", "node_id": "a", "show": {"thinking": True}})


def test_add_details_module_fills_every_field_key():
    """契约要求四个 key 齐全,缺的补 False。"""
    out = _one({"op": "add_details_module", "fields": {"answer": True, "analysis": True}})
    assert out == {
        "op": "add_details_module",
        "after": "end",
        "scope": "all",
        "fields": {"answer": True, "thinking": False, "analysis": True, "summary": False},
        "title": "参考答案",
    }


def test_unknown_op_is_rejected():
    with pytest.raises(AuthoringError, match="op must be one of"):
        _one({"op": "wrap_in_module", "node_ids": ["a"]})


def test_operations_are_bounded():
    with pytest.raises(AuthoringError, match="non-empty array"):
        prepare_operations([])
    with pytest.raises(AuthoringError, match="at most"):
        prepare_operations([{"op": "remove_nodes", "node_ids": ["a"]}] * (MAX_OPERATIONS + 1))


# --------------------------------------------------------------------------- #
# 工具契约
# --------------------------------------------------------------------------- #
async def test_prepare_hook_returns_normalized_arguments():
    prepared = await prepare_edit_composition(None, {
        "operations": [{"op": "remove_nodes", "node_ids": ["a"]}],
        "summary": "  删掉第三题  ",
    })
    assert prepared == {
        "operations": [{"op": "remove_nodes", "node_ids": ["a"]}],
        "summary": "删掉第三题",
    }


def test_edit_tools_are_scoped_to_the_composition_editor():
    """它们要改的是用户正开着的那份在编文档,离开编辑器就无从执行。"""
    for name in ("read_composition_outline", "edit_composition"):
        spec = ai_tools.get(name)
        assert spec.executor == "client"
        assert spec.scenes == frozenset({AgentScene.COMPOSITION_EDITOR})
        assert name not in {s.name for s in ai_tools.tools_for(AgentScene.QUESTION_LIBRARY)}


def test_edit_schema_is_gemini_safe():
    """Gemini 的 FunctionDeclaration 不吃 $ref/$defs/anyOf,原语的联合体只能扁平化表达。"""
    schema = json.dumps(ai_tools.get("edit_composition").to_openai_schema(), ensure_ascii=False)
    for banned in ('"$ref"', '"$defs"', '"anyOf"', '"oneOf"'):
        assert banned not in schema
