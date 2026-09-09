"""AI 工具集。各域模块显式导入以触发注册(PyInstaller 友好,不做动态扫描)。"""
from app.ai.tools.registry import all_tools, dispatch, get, openai_schemas, register

from app.ai.tools import library, questions  # noqa: E402,F401

__all__ = ["all_tools", "dispatch", "get", "openai_schemas", "register"]
