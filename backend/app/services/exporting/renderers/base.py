"""渲染器基类:消费 ExportDoc,产出磁盘文件路径。"""

from __future__ import annotations

from typing import Protocol

from app.services.exporting.contracts import ExportDoc


class Renderer(Protocol):
    ext: str

    def render(self, doc: ExportDoc) -> str:
        """把 ExportDoc 渲染成文件,返回文件路径(调用方负责清理)。"""
        ...
