"""AI 工具的执行契约。

工具返回结构化的 `ToolResult` 而不是裸字符串:`content` 喂模型,`ui` 携带需要前端
渲染的指令(如题目导入确认卡片)。此前这靠在返回文本里塞 `[CONFIRM_IMPORT:id]` 标记、
再由 SSE 层正则抠出来,协议极脆。
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.capabilities.context import ExecutionContext


class UIDirective(BaseModel):
    kind: Literal["proposal"]
    payload: Dict[str, Any]


def proposal_directive(kind: Literal["single", "batch"], ids: List[int]) -> UIDirective:
    return UIDirective(kind="proposal", payload={"type": kind, "ids": ids})


class ToolResult(BaseModel):
    content: str
    data: Optional[Dict[str, Any]] = None
    ui: List[UIDirective] = Field(default_factory=list)

    @classmethod
    def text(cls, content: str) -> "ToolResult":
        return cls(content=content)


ToolHandler = Callable[[ExecutionContext, Dict[str, Any]], Awaitable[ToolResult]]


class ToolSpec(BaseModel):
    """一个暴露给模型的工具。

    `parameters` 是面向 LLM 的 JSON Schema,刻意与 capability 的 input_model 解耦:
    模型产出的是松散的旧字符串形态(答案写成 "A"、选项是 label/content 对),
    由 handler 翻译成严格的 v2 入参。JSON Schema 也不由 pydantic 自动生成 ——
    Gemini 的 FunctionDeclaration 不吃 `$ref`/`$defs`/`anyOf`,手写 schema 更可控。

    `capability` 记录写操作最终落到哪个能力上;为 None 表示这是 AI 专属的只读工具。
    """
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: ToolHandler
    capability: Optional[str] = None
    mutating: bool = False

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
