"""工具注册表 —— 模型可见的工具集,以及统一的分发入口。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.ai.contracts import AgentScene, ToolResult, ToolSpec
from app.capabilities.context import ExecutionContext

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in _REGISTRY:
        raise RuntimeError(f"Duplicate tool name: {spec.name}")
    if spec.executor == "server" and spec.handler is None:
        raise RuntimeError(f"Server tool {spec.name} needs a handler")
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def all_tools() -> List[ToolSpec]:
    return list(_REGISTRY.values())


def tools_for(scene: AgentScene = AgentScene.UNSCOPED) -> List[ToolSpec]:
    return [spec for spec in _REGISTRY.values() if spec.available_in(scene)]


def openai_schemas(scene: AgentScene = AgentScene.UNSCOPED) -> List[Dict[str, Any]]:
    return [spec.to_openai_schema() for spec in tools_for(scene)]


async def dispatch(
    name: str,
    ctx: ExecutionContext,
    args: Dict[str, Any],
    *,
    scene: AgentScene = AgentScene.UNSCOPED,
) -> ToolResult:
    """执行一个工具。失败一律转成文本回喂模型,让它自我纠正而不是中断整轮对话。"""
    spec = get(name)
    if spec is None:
        return ToolResult.text(f"Error: Tool {name} not found")
    # 作用域硬拦截:模型可能从历史消息里学到工具名,不能只靠「不广播」。
    if not spec.available_in(scene):
        return ToolResult.text(
            f"Error: Tool {name} is not available on the current page ({scene.value})"
        )
    if spec.executor == "client" or spec.handler is None:
        # 前端工具由 AgentRunner 走 client_channel 完成往返,dispatch 手里没有事件流。
        return ToolResult.text(f"Error: Tool {name} must be executed by the client")
    try:
        return await spec.handler(ctx, args)
    except Exception as exc:  # noqa: BLE001 - 模型需要看到失败原因
        logger.exception("Tool execution error: %s", name)
        return ToolResult.text(f"Error executing tool: {exc}")
