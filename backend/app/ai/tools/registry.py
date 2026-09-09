"""工具注册表 —— 模型可见的工具集,以及统一的分发入口。"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.ai.contracts import ToolResult, ToolSpec
from app.capabilities.context import ExecutionContext

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    if spec.name in _REGISTRY:
        raise RuntimeError(f"Duplicate tool name: {spec.name}")
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def all_tools() -> List[ToolSpec]:
    return list(_REGISTRY.values())


def openai_schemas() -> List[Dict[str, Any]]:
    return [spec.to_openai_schema() for spec in _REGISTRY.values()]


async def dispatch(name: str, ctx: ExecutionContext, args: Dict[str, Any]) -> ToolResult:
    """执行一个工具。失败一律转成文本回喂模型,让它自我纠正而不是中断整轮对话。"""
    spec = get(name)
    if spec is None:
        return ToolResult.text(f"Error: Tool {name} not found")
    try:
        return await spec.handler(ctx, args)
    except Exception as exc:  # noqa: BLE001 - 模型需要看到失败原因
        logger.exception("Tool execution error: %s", name)
        return ToolResult.text(f"Error executing tool: {exc}")
