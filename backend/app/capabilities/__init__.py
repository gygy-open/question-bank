"""能力(用例)层。

各域模块在此显式导入以触发注册 —— 不用动态扫描,PyInstaller 打包后注册表才不会是空的。
"""
from .base import Authz, Capability, Scope
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

# 各域模块必须显式导入以触发注册(见模块 docstring)。放最后是因为它们要 import 上面的符号。
from . import assessments, compositions, questions  # noqa: E402,F401

__all__ = [
    "Authz",
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
