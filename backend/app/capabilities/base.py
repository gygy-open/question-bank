"""Capability —— 系统「能做什么」的可执行用例,是 API / AI 工具 / worker 共用的唯一业务入口。

与 `app/core/permissions.py` 的 `Permission`(能不能做)是两个概念,不要混用。

执行协议是三段式 `load → authorize → execute`:
`load` 把实体取出来一次,`authorize` 拿它的真实 subject 判权,`execute` 复用同一个对象,
避免「先加载判权、再加载执行」的双次查询。无实体的能力(如 create)让 `load` 返回 None 即可。

约定:
- 只抛 `DomainError`,不抛 `HTTPException` —— 传输语义由适配器决定。
- 一个 capability = 一个工作单元,自行 commit;registry 不额外包事务。
"""
from __future__ import annotations

import enum
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from app.core import permissions
from app.core.permissions import Permission

from .context import ExecutionContext
from .errors import Forbidden

TInput = TypeVar("TInput", bound=BaseModel)
TOutput = TypeVar("TOutput")

# 与 deps.require 抛出的 403 文案逐字一致,换载体不能换对外契约。
FORBIDDEN_DETAIL = "The user doesn't have enough privileges"


class Scope(str, enum.Enum):
    SUBJECT = "subject"  # 在某个学科作用域内判权
    GLOBAL = "global"    # 与学科无关


class Capability(ABC, Generic[TInput, TOutput]):
    name: ClassVar[str]
    description: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    permission: ClassVar[Permission | None]
    scope: ClassVar[Scope]
    mutating: ClassVar[bool]

    async def load(self, ctx: ExecutionContext, inp: TInput) -> Any:
        """取出被操作的实体,供 authorize 与 execute 共用。不存在/不可见时抛 NotFound。"""
        return None

    async def authorize(self, ctx: ExecutionContext, inp: TInput, target: Any) -> None:
        if self.permission is None:
            return
        subject_id = self.subject_for(ctx, inp, target) if self.scope is Scope.SUBJECT else None
        if not permissions.can(ctx.actor, self.permission, subject_id=subject_id):
            raise Forbidden(FORBIDDEN_DETAIL)

    def subject_for(self, ctx: ExecutionContext, inp: TInput, target: Any) -> int | None:
        """判权用的学科:优先实体自身的,其次入参的,最后回落上下文。"""
        for source in (target, inp):
            subject_id = getattr(source, "subject_id", None)
            if subject_id is not None:
                return subject_id
        return ctx.subject_id

    @abstractmethod
    async def execute(self, ctx: ExecutionContext, inp: TInput, target: Any) -> TOutput:
        ...
