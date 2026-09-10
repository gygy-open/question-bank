"""AI 工具的执行契约。

工具返回结构化的 `ToolResult` 而不是裸字符串:`content` 喂模型,`ui` 携带需要前端
渲染的指令(如题目导入确认卡片)。此前这靠在返回文本里塞 `[CONFIRM_IMPORT:id]` 标记、
再由 SSE 层正则抠出来,协议极脆。
"""
from __future__ import annotations

import enum
from typing import Any, Awaitable, Callable, Dict, FrozenSet, List, Literal, Optional

from pydantic import BaseModel, Field

from app.capabilities.context import ExecutionContext


class AgentScene(str, enum.Enum):
    """前端发起对话的页面场景,决定这一轮暴露哪些工具。

    与 `Surface`(api/chat/worker)正交:后者是「从哪个入口进来」,属于审计语义,不要混用。

    `UNSCOPED` 是「页面没声明场景」,此时暴露全部工具(与引入本机制前行为一致);
    只有页面显式声明了场景,才会按 `ToolSpec.scenes` 减面。

    它只用于减面(缩小攻击面 + 省 token),**不是授权机制** ——
    scene 由客户端自报且不可信,真正的门禁在 capability 层。
    """

    UNSCOPED = "unscoped"
    QUESTION_LIBRARY = "question_library"
    COMPOSITION_EDITOR = "composition_editor"
    IMPORT_REVIEW = "import_review"

    @classmethod
    def parse(cls, value: str | None) -> "AgentScene":
        """未知 scene 回落 UNSCOPED 而不是报错 —— 前后端版本漂移不能把聊天打挂。"""
        if not value:
            return cls.UNSCOPED
        try:
            return cls(value)
        except ValueError:
            return cls.UNSCOPED


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

    `scenes` 为 None 表示处处可用;给定集合则仅在这些页面场景下暴露。
    """
    model_config = {"arbitrary_types_allowed": True}

    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Optional[ToolHandler] = None
    capability: Optional[str] = None
    mutating: bool = False
    scenes: Optional[FrozenSet[AgentScene]] = None
    # client 工具没有服务端 handler:运行时把请求推给前端,等它回传结果。
    executor: Literal["server", "client"] = "server"

    def available_in(self, scene: AgentScene) -> bool:
        if self.scenes is None or scene is AgentScene.UNSCOPED:
            return True
        return scene in self.scenes

    def to_openai_schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
