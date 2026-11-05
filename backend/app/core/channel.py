"""当前请求 / 任务的「创建渠道」:经 MCP 由外部 Agent 发起的写入记为 ``mcp``。

用 ContextVar 传递,而不是在每条创建路径上加参数:``questions.created_via`` 的列默认值读取它,
因此单题创建、批量创建、派生题、导入等所有路径都会自动带上标记。

- MCP 每次工具调用时设置(``app/mcp_server/server.py``);
- Agent 经 MCP 排队的后台任务在 payload 里记 ``via``,worker 执行时按它设置。
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

MCP = "mcp"

current_channel: ContextVar[Optional[str]] = ContextVar("current_channel", default=None)


def channel_value() -> Optional[str]:
    """列默认值用:当前渠道(没有时为空)。"""
    return current_channel.get()


@contextmanager
def channel(value: Optional[str]) -> Iterator[None]:
    """在一段代码内设置当前渠道。"""
    token = current_channel.set(value)
    try:
        yield
    finally:
        current_channel.reset(token)
