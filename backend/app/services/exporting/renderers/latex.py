"""LaTeX 渲染器:RichDoc → LaTeX 直连(无 pandoc)+ Jinja 模板 → .tex + images 打包 zip。"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader

from app.services.exporting.answer import answer_spec_to_inline
from app.services.exporting.contracts import ExportDoc, ExportQuestion, ExportSection
from app.services.exporting.images import ImageResolver
from app.services.exporting.richdoc.latex import (
    latex_escape,
    rich_doc_to_latex,
    rich_inline_to_latex,
)

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "templates",
)


class LatexRenderer:
    ext = "zip"

    def __init__(self) -> None:
        self.images = ImageResolver()
        self.jinja = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            block_start_string="\\BLOCK{",
            block_end_string="}",
            variable_start_string="\\VAR{",
            variable_end_string="}",
            comment_start_string="\\#{",
            comment_end_string="}",
            line_statement_prefix="%%",
            line_comment_prefix="%#",
            trim_blocks=True,
            autoescape=False,
        )

    def render(self, doc: ExportDoc) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            images_dir = base / "images"
            images_dir.mkdir()
            seen: dict[str, str] = {}

            def image_path(src: str) -> Optional[str]:
                resolved = self.images.resolve(src)
                if resolved is None:
                    return None
                if src not in seen:
                    dst = images_dir / resolved.name
                    shutil.copy2(resolved, dst)
                    seen[src] = f"images/{resolved.name}"
                return seen[src]

            latex = self._render_tex(doc, image_path)
            (base / f"{doc.title}.tex").write_text(latex, encoding="utf-8")

            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(zip_fd)
            os.remove(zip_path)
            shutil.make_archive(zip_path[:-4], "zip", base)
            return zip_path

    def _render_tex(self, doc: ExportDoc, image_path) -> str:
        sections = [self._section_ctx(s, image_path) for s in doc.sections]
        appendix = [self._section_ctx(s, image_path) for s in doc.appendix]
        template = self.jinja.get_template("exam_paper.tex.j2")
        return template.render(
            title=doc.title,
            sections=sections,
            appendix_sections=appendix,
            has_appendix=doc.has_appendix,
        )

    def _section_ctx(self, section: ExportSection, image_path) -> dict[str, Any]:
        return {
            "title": section.title,
            "questions": [self._q_ctx(q, image_path) for q in section.questions],
        }

    def _q_ctx(self, q: ExportQuestion, image_path) -> dict[str, Any]:
        answer_tex = ""
        if q.answer is not None:
            answer_tex = rich_inline_to_latex(answer_spec_to_inline(q.answer, q.options), image_path)
        return {
            "content_tex": rich_doc_to_latex(q.stem, image_path),
            "options_tex": [rich_doc_to_latex(o.content, image_path) for o in q.options],
            "answer_tex": answer_tex,
            "thinking_tex": rich_doc_to_latex(q.thinking, image_path) if q.thinking else "",
            "analysis_tex": rich_doc_to_latex(q.analysis, image_path) if q.analysis else "",
            "summary_tex": rich_doc_to_latex(q.summary, image_path) if q.summary else "",
            "source_tex": latex_escape(q.source) if q.source else "",
            "reserve_space": q.reserve_space,
        }
