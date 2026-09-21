"""组稿增量编辑原语 —— 服务端校验 + 归一,真正的应用发生在前端画布上。

为什么应用在前端:AST 代数(插入/删除/移动/规范化)已经在 `compositionDocument.ts` 里实现了
一份,后端只保留「全量替换 + 校验」这一个持久化边界;而且只有前端手里有用户未保存的
在编文档,以及做 diff 预览所需的 before/after。

为什么还要过一趟服务端:`rich_text` 的正文是 Markdown,md → RichDoc 的转换器(含公式与表格)
只在后端有一份,前端再实现一份必然漂移。所以这里在推给前端之前先把 Markdown 转好,
前端只做纯结构操作。顺带把模型给的松散入参收敛掉,不合法直接回喂模型改,不浪费一轮往返。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.schemas.composition import ANSWER_FIELD_KEYS
from app.services.composition_authoring import AuthoringError, markdown_to_rich_doc_blocks

OP_INSERT_NODES = "insert_nodes"
OP_REMOVE_NODES = "remove_nodes"
OP_MOVE_NODE = "move_node"
OP_SET_NODE_PROPS = "set_node_props"
OP_SHOW_QUESTION_FIELDS = "show_question_fields"
OP_ADD_DETAILS_MODULE = "add_details_module"

OPERATIONS = (
    OP_INSERT_NODES,
    OP_REMOVE_NODES,
    OP_MOVE_NODE,
    OP_SET_NODE_PROPS,
    OP_SHOW_QUESTION_FIELDS,
    OP_ADD_DETAILS_MODULE,
)

# question_details 不在其中:它有 answer_item 派生这层结构性惯用法,走 add_details_module。
INSERTABLE_NODE_TYPES = ("heading", "rich_text", "question", "page_break", "answer_space")

# 节点 id 之外的插入锚点。
ANCHOR_START = "start"
ANCHOR_END = "end"

SHOW_VALUES = ("show", "hide", "inherit")
DETAIL_SCOPES = ("all", "before")
ANSWER_SPACE_STYLES = ("blank", "lined")

# 可被 set_node_props 改写的属性,以及它们的校验方式。节点 id / 内容 / 软指针 / question_id
# 都是系统拥有的字段,不在此列。
SETTABLE_PROPS = ("number", "score", "level", "lines", "style", "scope", "fields")

MAX_OPERATIONS = 50
MAX_NODES_PER_INSERT = 50


def _require_dict(value: Any, *, field: str) -> Dict[str, Any]:
    if not isinstance(value, dict):
        raise AuthoringError(f"{field} must be an object")
    return value


def _require_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthoringError(f"{field} must be a non-empty string")
    return value.strip()


def _require_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuthoringError(f"{field} must be an integer")
    return value


def _require_number(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuthoringError(f"{field} must be a number")
    return value


def _require_enum(value: Any, allowed: tuple, *, field: str) -> str:
    if value not in allowed:
        raise AuthoringError(f"{field} must be one of {list(allowed)}, got {value!r}")
    return value


def _require_id_list(value: Any, *, field: str) -> List[str]:
    if not isinstance(value, list) or not value:
        raise AuthoringError(f"{field} must be a non-empty array of node ids")
    return [_require_str(item, field=f"{field}[{i}]") for i, item in enumerate(value)]


def _anchor(value: Any, *, field: str) -> str:
    """插入锚点:节点 id,或 'start' / 'end'。缺省为 'end'。"""
    if value is None:
        return ANCHOR_END
    return _require_str(value, field=field)


def _detail_fields(value: Any, *, field: str) -> Dict[str, bool]:
    given = _require_dict(value, field=field)
    unknown = set(given) - set(ANSWER_FIELD_KEYS)
    if unknown:
        raise AuthoringError(
            f"{field} keys must be within {list(ANSWER_FIELD_KEYS)}, got {sorted(unknown)}"
        )
    # 契约要求四个 key 齐全,缺的补 False。
    return {k: bool(given.get(k, False)) for k in ANSWER_FIELD_KEYS}


def _insert_node(spec: Any, *, field: str) -> Dict[str, Any]:
    spec = _require_dict(spec, field=field)
    node_type = spec.get("type")
    if node_type not in INSERTABLE_NODE_TYPES:
        raise AuthoringError(
            f"{field}.type must be one of {list(INSERTABLE_NODE_TYPES)}, got {node_type!r}"
        )

    if node_type == "rich_text":
        blocks = markdown_to_rich_doc_blocks(spec.get("markdown") or "")
        if not blocks:
            raise AuthoringError(f"{field} rich_text requires non-empty markdown")
        # 前端拿到的是转换好的 RichDoc,不再需要(也没有能力)解析 Markdown。
        return {"type": "rich_text", "rich_doc_blocks": blocks}

    if node_type == "heading":
        level = spec.get("level")
        level = 2 if level is None else _require_int(level, field=f"{field}.level")
        if not 1 <= level <= 4:
            raise AuthoringError(f"{field}.level must be in 1..4")
        return {
            "type": "heading",
            "text": _require_str(spec.get("text"), field=f"{field}.text"),
            "level": level,
        }

    if node_type == "question":
        out: Dict[str, Any] = {
            "type": "question",
            "question_id": _require_int(spec.get("question_id"), field=f"{field}.question_id"),
        }
        if spec.get("number") is not None:
            out["number"] = str(spec["number"])[:16]
        if spec.get("score") is not None:
            out["score"] = _require_number(spec["score"], field=f"{field}.score")
        return out

    if node_type == "answer_space":
        # 缺省值不在此层定下来:留空交给 composition_authoring 按题型/分值推导。
        out: Dict[str, Any] = {"type": "answer_space"}
        lines = spec.get("lines")
        if lines is not None:
            lines = _require_int(lines, field=f"{field}.lines")
            if lines < 1:
                raise AuthoringError(f"{field}.lines must be >= 1")
            out["lines"] = lines
        style = spec.get("style")
        if style is not None:
            out["style"] = _require_enum(style, ANSWER_SPACE_STYLES, field=f"{field}.style")
        return out

    return {"type": "page_break"}


def _settable_props(value: Any, *, field: str) -> Dict[str, Any]:
    given = _require_dict(value, field=field)
    unknown = set(given) - set(SETTABLE_PROPS)
    if unknown:
        raise AuthoringError(
            f"{field} keys must be within {list(SETTABLE_PROPS)}, got {sorted(unknown)}"
        )
    out: Dict[str, Any] = {}
    for key, raw in given.items():
        if raw is None:
            continue
        if key == "number":
            out[key] = str(raw)[:16]
        elif key == "score":
            out[key] = _require_number(raw, field=f"{field}.score")
        elif key == "level":
            level = _require_int(raw, field=f"{field}.level")
            if not 1 <= level <= 4:
                raise AuthoringError(f"{field}.level must be in 1..4")
            out[key] = level
        elif key == "lines":
            lines = _require_int(raw, field=f"{field}.lines")
            if lines < 1:
                raise AuthoringError(f"{field}.lines must be >= 1")
            out[key] = lines
        elif key == "style":
            out[key] = _require_enum(raw, ANSWER_SPACE_STYLES, field=f"{field}.style")
        elif key == "scope":
            out[key] = _require_enum(raw, DETAIL_SCOPES, field=f"{field}.scope")
        elif key == "fields":
            out[key] = _detail_fields(raw, field=f"{field}.fields")
    return out


def _clear_props(value: Any, *, field: str) -> List[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AuthoringError(f"{field} must be an array of property names")
    out: List[str] = []
    for i, item in enumerate(value):
        out.append(_require_enum(item, SETTABLE_PROPS, field=f"{field}[{i}]"))
    return out


def _show_map(value: Any, *, field: str) -> Dict[str, str]:
    given = _require_dict(value, field=field)
    unknown = set(given) - set(ANSWER_FIELD_KEYS)
    if unknown:
        raise AuthoringError(
            f"{field} keys must be within {list(ANSWER_FIELD_KEYS)}, got {sorted(unknown)}"
        )
    out = {k: _require_enum(v, SHOW_VALUES, field=f"{field}.{k}") for k, v in given.items()}
    if not out:
        raise AuthoringError(f"{field} must set at least one field")
    return out


def _prepare_one(spec: Any, *, field: str) -> Dict[str, Any]:
    spec = _require_dict(spec, field=field)
    op = spec.get("op")
    if op not in OPERATIONS:
        raise AuthoringError(f"{field}.op must be one of {list(OPERATIONS)}, got {op!r}")

    if op == OP_INSERT_NODES:
        nodes = spec.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            raise AuthoringError(f"{field}.nodes must be a non-empty array")
        if len(nodes) > MAX_NODES_PER_INSERT:
            raise AuthoringError(f"{field}.nodes must hold at most {MAX_NODES_PER_INSERT} nodes")
        return {
            "op": op,
            "after": _anchor(spec.get("after"), field=f"{field}.after"),
            "nodes": [_insert_node(n, field=f"{field}.nodes[{i}]") for i, n in enumerate(nodes)],
        }

    if op == OP_REMOVE_NODES:
        return {"op": op, "node_ids": _require_id_list(spec.get("node_ids"), field=f"{field}.node_ids")}

    if op == OP_MOVE_NODE:
        before = spec.get("before")
        return {
            "op": op,
            "node_id": _require_str(spec.get("node_id"), field=f"{field}.node_id"),
            # 省略 before = 移到末尾。
            "before": None if before is None else _require_str(before, field=f"{field}.before"),
        }

    if op == OP_SET_NODE_PROPS:
        props = _settable_props(spec.get("props") or {}, field=f"{field}.props")
        clear = _clear_props(spec.get("clear"), field=f"{field}.clear")
        if not props and not clear:
            raise AuthoringError(f"{field} must set or clear at least one property")
        return {
            "op": op,
            "node_id": _require_str(spec.get("node_id"), field=f"{field}.node_id"),
            "props": props,
            "clear": clear,
        }

    if op == OP_SHOW_QUESTION_FIELDS:
        return {
            "op": op,
            "node_id": _require_str(spec.get("node_id"), field=f"{field}.node_id"),
            "show": _show_map(spec.get("show"), field=f"{field}.show"),
        }

    title: Optional[str] = spec.get("title")
    return {
        "op": OP_ADD_DETAILS_MODULE,
        "after": _anchor(spec.get("after"), field=f"{field}.after"),
        "scope": _require_enum(spec.get("scope") or "all", DETAIL_SCOPES, field=f"{field}.scope"),
        "fields": _detail_fields(spec.get("fields") or {"answer": True}, field=f"{field}.fields"),
        "title": (title.strip() if isinstance(title, str) and title.strip() else "参考答案"),
    }


def prepare_operations(specs: Any) -> List[Dict[str, Any]]:
    """校验并归一模型给的原语列表,Markdown 在这里转成 RichDoc。不合法直接抛 AuthoringError。"""
    if not isinstance(specs, list) or not specs:
        raise AuthoringError("operations must be a non-empty array")
    if len(specs) > MAX_OPERATIONS:
        raise AuthoringError(f"operations must hold at most {MAX_OPERATIONS} entries")
    return [_prepare_one(spec, field=f"operations[{i}]") for i, spec in enumerate(specs)]
