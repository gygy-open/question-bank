"""能力注册表 —— 按 name 索引的唯一真相源。

API 端点、AI 工具、worker 都经 `run()` 进来,拿到同一套业务逻辑与鉴权。
"""
from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel

from .base import Capability
from .context import ExecutionContext

_REGISTRY: dict[str, Capability] = {}

# 允许 permission=None 的能力白名单。
# 组稿域历史上就没有鉴权门禁(见 repo 决策记录),本期只做搬迁不改行为,
# 故在此登记为「已知缺口」。test_capability_registry 断言集合完全相等,防止缺口静默增长。
UNGATED_ALLOWLIST: frozenset[str] = frozenset()


def register(cls: type[Capability]) -> type[Capability]:
    """类装饰器:实例化并注册(能力无状态,单例即可)。重名在导入期就炸。"""
    cap = cls()
    if cap.name in _REGISTRY:
        raise RuntimeError(f"Duplicate capability name: {cap.name}")
    _REGISTRY[cap.name] = cap
    return cls


def get(name: str) -> Capability:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise LookupError(f"Unknown capability: {name}") from None


def all_capabilities() -> Iterable[Capability]:
    return tuple(_REGISTRY.values())


async def run(name: str, ctx: ExecutionContext, inp: BaseModel) -> Any:
    cap = get(name)
    target = await cap.load(ctx, inp)
    await cap.authorize(ctx, inp, target)
    return await cap.execute(ctx, inp, target)
