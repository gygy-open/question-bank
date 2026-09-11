"""组稿增量编辑工具 —— 在用户正打开的组稿编辑器里读大纲、改 AST。

只在 `composition_editor` 场景暴露,且都是 client 工具:编辑要落在用户手里那份(可能有
未保存改动的)在编文档上,读也必须同源,否则模型看到的 node id 和实际编辑目标对不上。

改动**不会直接保存**。前端在内存里应用完这批原语后算出 before/after 变更清单,
画布切到预览态等用户点「应用 / 放弃」。工具本身立刻返回(远小于票据超时),
不占着 run 等人 —— 人工确认可能要几分钟,远超 30s 票据与 180s run 预算。
"""
from __future__ import annotations

from typing import Any, Dict

from app.ai import client_channel
from app.ai.contracts import AgentScene, ToolSpec
from app.ai.tools.registry import register
from app.capabilities.context import ExecutionContext
from app.schemas.composition import ANSWER_FIELD_KEYS
from app.services.composition_ops import (
    ANSWER_SPACE_STYLES,
    DETAIL_SCOPES,
    INSERTABLE_NODE_TYPES,
    OPERATIONS,
    SETTABLE_PROPS,
    SHOW_VALUES,
    prepare_operations,
)

_COMPOSITION_EDITOR = frozenset({AgentScene.COMPOSITION_EDITOR})

READ_OUTLINE_PARAMS = {
    "type": "object",
    "properties": {},
    "required": [],
}

_INSERT_NODE_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": list(INSERTABLE_NODE_TYPES),
            "description": "要插入的节点类型。参考答案模块请改用 add_details_module。",
        },
        "text": {"type": "string", "description": "heading 的标题文字。"},
        "level": {"type": "integer", "description": "heading 的层级 1-4,缺省 2。"},
        "markdown": {
            "type": "string",
            "description": "rich_text 的正文,Markdown 格式(支持公式与表格),服务端会转成富文本。",
        },
        "question_id": {"type": "integer", "description": "question 引用的题库题目 id。"},
        "number": {"type": "string", "description": "question 的题号。"},
        "score": {"type": "number", "description": "question 的分值。"},
        "lines": {"type": "integer", "description": "answer_space 的行数,缺省 4。"},
        "style": {
            "type": "string",
            "enum": list(ANSWER_SPACE_STYLES),
            "description": "answer_space 的样式,缺省 lined。",
        },
    },
    "required": ["type"],
}

_SHOW_SCHEMA = {
    "type": "object",
    "properties": {
        key: {
            "type": "string",
            "enum": list(SHOW_VALUES),
            "description": f"{key} 字段:show 显示 / hide 隐藏 / inherit 跟随稿件全局设置。",
        }
        for key in ANSWER_FIELD_KEYS
    },
}

_FIELDS_SCHEMA = {
    "type": "object",
    "properties": {key: {"type": "boolean"} for key in ANSWER_FIELD_KEYS},
}

# 扁平 object + op 枚举,而不是 oneOf —— Gemini 的 FunctionDeclaration 不吃 anyOf/$ref。
_OPERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "op": {"type": "string", "enum": list(OPERATIONS), "description": "要执行的操作。"},
        "after": {
            "type": "string",
            "description": "insert_nodes / add_details_module 的插入位置:目标节点 id(插到它后面),"
                           "或 'start' / 'end'。缺省 'end'。",
        },
        "nodes": {
            "type": "array",
            "items": _INSERT_NODE_SCHEMA,
            "description": "insert_nodes 要插入的节点列表,按版面顺序。",
        },
        "node_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "remove_nodes 要删除的节点 id 列表。",
        },
        "node_id": {
            "type": "string",
            "description": "move_node / set_node_props / show_question_fields 的目标节点 id。",
        },
        "before": {
            "type": "string",
            "description": "move_node 的落点:移到该节点之前;省略表示移到末尾。",
        },
        "props": {
            "type": "object",
            "properties": {
                "number": {"type": "string", "description": "question 的题号。"},
                "score": {"type": "number", "description": "question 的分值。"},
                "level": {"type": "integer", "description": "heading 的层级 1-4。"},
                "lines": {"type": "integer", "description": "answer_space 的行数。"},
                "style": {"type": "string", "enum": list(ANSWER_SPACE_STYLES)},
                "scope": {
                    "type": "string",
                    "enum": list(DETAIL_SCOPES),
                    "description": "question_details 收录范围:all 全稿 / before 仅模块之前。",
                },
                "fields": _FIELDS_SCHEMA,
            },
            "description": "set_node_props 要写入的属性,按目标节点类型取用。",
        },
        "clear": {
            "type": "array",
            "items": {"type": "string", "enum": list(SETTABLE_PROPS)},
            "description": "set_node_props 要清除的属性名(如清空分值用 ['score'])。",
        },
        "show": {
            **_SHOW_SCHEMA,
            "description": "show_question_fields 对某道题的答案/思路/解析/小结的显隐覆盖。",
        },
        "scope": {
            "type": "string",
            "enum": list(DETAIL_SCOPES),
            "description": "add_details_module 的收录范围,缺省 all。",
        },
        "fields": {
            **_FIELDS_SCHEMA,
            "description": "add_details_module 模块内展示哪些字段,缺省仅答案。",
        },
        "title": {"type": "string", "description": "add_details_module 的模块标题,缺省「参考答案」。"},
    },
    "required": ["op"],
}

EDIT_COMPOSITION_PARAMS = {
    "type": "object",
    "properties": {
        "operations": {
            "type": "array",
            "items": _OPERATION_SCHEMA,
            "description": "按顺序执行的一批操作。",
        },
        "summary": {
            "type": "string",
            "description": "一句话说明这批改动做了什么,会展示给用户看。",
        },
    },
    "required": ["operations"],
}


async def prepare_edit_composition(
    ctx: ExecutionContext, args: Dict[str, Any]
) -> Dict[str, Any]:
    """服务端先把 Markdown 正文转成 RichDoc 并校验原语,前端只做纯结构操作。"""
    out: Dict[str, Any] = {"operations": prepare_operations(args.get("operations"))}
    summary = args.get("summary")
    if isinstance(summary, str) and summary.strip():
        out["summary"] = summary.strip()
    return out


if client_channel.is_enabled():
    register(ToolSpec(
        name="read_composition_outline",
        description=(
            "读取用户当前正在编辑的稿件大纲:每个节点的 id、类型、关键属性与内容摘要,"
            "保留参考答案模块的嵌套层级。**改动稿件之前必须先调用它拿到节点 id** —— "
            "edit_composition 全靠 id 定位,凭空猜的 id 一定会失败。"
        ),
        parameters=READ_OUTLINE_PARAMS,
        scenes=_COMPOSITION_EDITOR,
        executor="client",
    ))

    register(ToolSpec(
        name="edit_composition",
        description=(
            "对用户当前正在编辑的稿件做增量修改:插入/删除/移动节点、改题号分值标题层级、"
            "切换某道题的答案解析显隐、添加参考答案模块。"
            "节点 id 来自 read_composition_outline,请先读再改。"
            "改动会先以预览形式呈现给用户确认,**不会立即保存**,所以不要假设它已经生效;"
            "也不要用它做整份重写 —— 那是新建空稿件时 write_composition_nodes 的职责。"
        ),        parameters=EDIT_COMPOSITION_PARAMS,
        scenes=_COMPOSITION_EDITOR,
        executor="client",
        prepare=prepare_edit_composition,
    ))
