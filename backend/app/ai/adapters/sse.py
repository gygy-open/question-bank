"""AgentEvent → SSE。

刻意沿用前端已在消费的事件名(message / action / action_result / proposal / done),
新的 envelope 只在后端内部流转,这样运行时重构对前端零影响。等前端工具落地、
需要 interrupt/resume 时再谈对外协议改版。
"""
from __future__ import annotations

import json
from typing import Any, Iterator

from app.ai.events import (
    AgentEvent,
    RunFailed,
    RunFinished,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)

_PREVIEW_LIMIT = 200


def sse_pack(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def to_sse(event: AgentEvent) -> Iterator[str]:
    if isinstance(event, TextDelta):
        yield sse_pack("message", event.text)
    elif isinstance(event, ToolCallStarted):
        yield sse_pack("action", {"tool": event.name, "input": event.arguments})
    elif isinstance(event, ToolCallFinished):
        for directive in event.ui:
            yield sse_pack(directive.kind, directive.payload)
        content = event.content
        preview = content[:_PREVIEW_LIMIT] + "..." if len(content) > _PREVIEW_LIMIT else content
        yield sse_pack("action_result", {"tool": event.name, "output": preview})
    elif isinstance(event, RunFailed):
        yield sse_pack("message", f"\n[Error: {event.error}]")
