"""前端执行的工具 —— 由 AgentRunner 经 client_channel 推给浏览器完成。

只在单进程部署下注册(见 `client_channel.is_enabled`),多进程时回传会落到别的 worker。

**参数刻意是结构化的,不接受原始 URL 或路径字符串。** 文档导入链路会把外部内容喂给
模型,一旦存在提示注入,能传任意路径的跳转工具就等于开放重定向。这里只收 id 与枚举,
真实 URL 由前端拼。
"""
from __future__ import annotations

from app.ai import client_channel
from app.ai.contracts import ToolSpec
from app.ai.tools.registry import register
from app.models.composition import ScopeType

OPEN_COMPOSITION_PARAMS = {
    "type": "object",
    "properties": {
        "composition_id": {"type": "integer", "description": "要打开的稿件 id。"},
        "scope": {
            "type": "string",
            "enum": [s.value for s in ScopeType],
            "description": "稿件的范围,必须与建稿时一致。",
        },
    },
    "required": ["composition_id", "scope"],
}

# 枚举值,不是路径 —— 前端(useAiClientTools.ts 的 PAGE_ROUTES)据此映射真实路由,两侧手工保持一致。
PAGE_KEYS = (
    "question_library",
    "knowledge_points",
    "subjects",
    "tags",
    "compositions_shared",
    "compositions_personal",
    "import_review",
    "dashboard",
)

OPEN_PAGE_PARAMS = {
    "type": "object",
    "properties": {
        "page": {
            "type": "string",
            "enum": list(PAGE_KEYS),
            "description": "要打开的页面标识。",
        },
    },
    "required": ["page"],
}


if client_channel.is_enabled():
    register(ToolSpec(
        name="open_composition",
        description=(
            "在用户的浏览器里打开指定稿件的组稿编辑器。"
            "通常在用 write_composition_nodes 写完内容后调用,好让用户直接看到成果。"
        ),
        parameters=OPEN_COMPOSITION_PARAMS,
        executor="client",
    ))

    register(ToolSpec(
        name="open_page",
        description=(
            "在用户的浏览器里跳转到题库、知识点、学科、标签、组稿列表、导入审阅或首页等"
            "列表/管理类页面。若要打开某一份具体的稿件,应使用 open_composition 而不是这个工具。"
        ),
        parameters=OPEN_PAGE_PARAMS,
        executor="client",
    ))
