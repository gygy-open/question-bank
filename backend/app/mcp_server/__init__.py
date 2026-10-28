"""MCP(Model Context Protocol)服务:让外部 AI 客户端以用户身份调用题库能力。"""
from .server import mcp_asgi_app, run_mcp

MCP_PATH = "/api/mcp"

__all__ = ["MCP_PATH", "mcp_asgi_app", "run_mcp"]
