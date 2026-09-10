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
