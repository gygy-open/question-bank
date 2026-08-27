"""format → 组稿导出 Renderer 解析(镜像 Paper 的 registry.py)。"""

from __future__ import annotations

from typing import Protocol

from app.schemas.paper import OutputFormat
from app.services.exporting.composition_contracts import CompositionExportDoc
from app.services.exporting.renderers.composition_docx import CompositionDocxRenderer
from app.services.exporting.renderers.composition_latex import CompositionLatexRenderer


class CompositionRenderer(Protocol):
    ext: str

    def render(self, doc: CompositionExportDoc) -> str:
        """把 CompositionExportDoc 渲染成文件,返回文件路径(调用方负责清理)。"""
        ...


_RENDERERS = {
    OutputFormat.LATEX: CompositionLatexRenderer,
    OutputFormat.DOCX: CompositionDocxRenderer,
}


def composition_renderer_for(fmt: OutputFormat) -> CompositionRenderer:
    try:
        return _RENDERERS[fmt]()
    except KeyError as exc:
        raise ValueError(f"Unsupported export format: {fmt}") from exc
