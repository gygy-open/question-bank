"""Agent 运行时产生的事件 —— 与传输无关。

SSE 适配器把它们翻译成前端已有的事件名;将来 MCP / worker 复用同一套。
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

from app.ai.contracts import UIDirective


class TextDelta(BaseModel):
    type: Literal["text.delta"] = "text.delta"
    text: str


class ToolCallStarted(BaseModel):
    type: Literal["tool.call"] = "tool.call"
    tool_call_id: str
    name: str
    arguments: Any


class AssistantTurn(BaseModel):
    """一轮带工具调用的助手输出。存在的目的是让调用方把它落库 ——
    运行时不知道 chat_messages 表长什么样。不产生任何对外 SSE 帧。"""
    type: Literal["assistant.turn"] = "assistant.turn"
    run_id: str
    text: str
    tool_calls: List[Dict[str, Any]]


class ToolCallFinished(BaseModel):
    type: Literal["tool.result"] = "tool.result"
    run_id: str
    tool_call_id: str
    name: str
    content: str
    ui: List[UIDirective] = Field(default_factory=list)


class RunFinished(BaseModel):
    type: Literal["run.finished"] = "run.finished"
    run_id: str
    text: str
    stop_reason: Literal["completed", "budget_exhausted"] = "completed"


class RunFailed(BaseModel):
    type: Literal["run.failed"] = "run.failed"
    run_id: Optional[str] = None
    error: str


AgentEvent = Union[
    TextDelta, ToolCallStarted, AssistantTurn, ToolCallFinished, RunFinished, RunFailed
]
