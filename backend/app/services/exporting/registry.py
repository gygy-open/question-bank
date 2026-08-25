"""format → Renderer 解析。新增格式 = 加一个渲染器类 + 注册一行。"""

from __future__ import annotations

from app.schemas.paper import OutputFormat
from app.services.exporting.renderers.base import Renderer
from app.services.exporting.renderers.docx import DocxRenderer
from app.services.exporting.renderers.latex import LatexRenderer

_RENDERERS = {
    OutputFormat.LATEX: LatexRenderer,
    OutputFormat.DOCX: DocxRenderer,
}


def renderer_for(fmt: OutputFormat) -> Renderer:
    try:
        return _RENDERERS[fmt]()
    except KeyError as exc:
        raise ValueError(f"Unsupported export format: {fmt}") from exc
