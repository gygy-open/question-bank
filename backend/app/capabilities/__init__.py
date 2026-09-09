"""能力(用例)层。

各域模块在此显式导入以触发注册 —— 不用动态扫描,PyInstaller 打包后注册表才不会是空的。
"""
from .base import Capability, Scope
from .context import ExecutionContext, Surface
from .errors import (
    Conflict,
    DomainError,
    Forbidden,
    Invalid,
    NotFound,
    Unprocessable,
)
from .registry import UNGATED_ALLOWLIST, all_capabilities, get, register, run

__all__ = [
    "Capability",
    "Scope",
    "ExecutionContext",
    "Surface",
    "DomainError",
    "NotFound",
    "Forbidden",
    "Invalid",
    "Conflict",
    "Unprocessable",
    "UNGATED_ALLOWLIST",
    "all_capabilities",
    "get",
    "register",
    "run",
]
