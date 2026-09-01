"""CompositionExportDoc → LaTeX(纯 Python 字符串拼接,不复用 Paper 的 Jinja 模板/exam
文档类:题号已在装配阶段冻结为字符串,不能交给 exam 的 \\question 自动计数)+ images 打包 zip。
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Optional

from app.services.exporting.answer import answer_spec_to_inline
from app.services.exporting.composition_contracts import (
    CompositionExportDoc,
    CompositionExportNode,
    ExportAnswerEntry,
    ExportAnswerSpaceNode,
    ExportHeadingNode,
    ExportOption,
    ExportPageBreakNode,
    ExportQuestionDetailsNode,
    ExportQuestionNode,
    ExportRichTextNode,
    RichDoc,
)
from app.services.exporting.images import ImageResolver
from app.services.exporting.richdoc.latex import latex_escape, rich_doc_to_latex, rich_inline_to_latex

ImagePathFn = Any  # Optional[Callable[[str], Optional[str]]],与 richdoc.latex 保持一致

_PREAMBLE = r"""\documentclass[12pt,a4paper]{article}
\usepackage[margin=2cm]{geometry}
\usepackage[UTF8, scheme=plain]{ctex}
\usepackage{amsmath, amssymb}
\usepackage{graphicx}
\usepackage{multicol}
\usepackage{booktabs}
\usepackage{longtable}
\providecommand{\tightlist}{%
  \setlength{\itemsep}{0pt}\setlength{\parskip}{0pt}}
"""

_HEADING_CMD = {1: "section*", 2: "subsection*", 3: "subsubsection*", 4: "paragraph*"}
_LABELS = (("thinking", "【思路】"), ("analysis", "【解析】"), ("summary", "【总结】"))
# 与前端画布一致：有题号时题干用 hangindent 折行对齐首行文字起点，选项同量右移。
_NUMBER_INDENT = "1.5em"
# 作答横线单行占高（与 blank 每行 1\baselineskip 视觉相近）。
_ANSWER_SPACE_LINE_HEIGHT = "1.5\\baselineskip"


def _format_score(score: float) -> str:
    return f"{score:g}"


class CompositionLatexRenderer:
    ext = "zip"

    def __init__(self) -> None:
        self.images = ImageResolver()

    def render(self, doc: CompositionExportDoc) -> str:
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

            tex = self._render_tex(doc, image_path)
            (base / f"{doc.title}.tex").write_text(tex, encoding="utf-8")

            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(zip_fd)
            os.remove(zip_path)
            shutil.make_archive(zip_path[:-4], "zip", base)
            return zip_path

    # --- 文档骨架 --------------------------------------------------------- #
    def _render_tex(self, doc: CompositionExportDoc, image_path: ImagePathFn) -> str:
        # doc.title 只用于导出文件名(.tex 文件名/下载文件名),正文完全按画布节点渲染,不额外插入标题行。
        parts = [_PREAMBLE, "\\begin{document}\n"]
        for node in doc.nodes:
            parts.append(self._render_node(node, image_path))
        parts.append("\\end{document}\n")
        return "\n".join(parts)

    # --- 节点 dispatch --------------------------------------------------- #
    def _render_node(self, node: CompositionExportNode, image_path: ImagePathFn) -> str:
        if isinstance(node, ExportRichTextNode):
            return rich_doc_to_latex(node.content, image_path) + "\n"
        if isinstance(node, ExportHeadingNode):
            return self._render_heading(node, image_path)
        if isinstance(node, ExportQuestionNode):
            return self._render_question(node, image_path)
        if isinstance(node, ExportPageBreakNode):
            return "\\clearpage\n"
        if isinstance(node, ExportAnswerSpaceNode):
            return self._render_answer_space(node)
        if isinstance(node, ExportQuestionDetailsNode):
            return self._render_question_details(node, image_path)
        raise ValueError(f"Unsupported composition export node: {type(node)!r}")

    def _render_heading(self, node: ExportHeadingNode, image_path: ImagePathFn) -> str:
        # heading content 恒为单段落纯行内内容(schema 已保证),rich_doc_to_latex 的输出可直接
        # 塞进 sectioning 命令的参数里。
        text = rich_doc_to_latex(node.content, image_path)
        cmd = _HEADING_CMD.get(node.level, "subsubsection*")
        return f"\\{cmd}{{{text}}}\n"

    def _render_answer_space(self, node: ExportAnswerSpaceNode) -> str:
        # 每行按固定行距预留;lined 逐行画满宽横线,blank 只留等高垂直空白。
        lines = max(1, node.lines)
        if node.style == "lined":
            row = "\\noindent\\rule{\\linewidth}{0.4pt}\\par\\vspace{%s}\n" % _ANSWER_SPACE_LINE_HEIGHT
            return "\\par\\vspace{0.3\\baselineskip}\n" + row * lines
        return "\\par\\vspace{%d\\baselineskip}\n" % lines

    def _render_question(self, q: ExportQuestionNode, image_path: ImagePathFn) -> str:
        # 题号(粗体)+ 分值(斜体)同挤在题干首段前,而非各占一行,与编辑器内联展示口径一致。
        hang = f"\\hangindent={_NUMBER_INDENT}\\hangafter=1 " if q.number else ""
        prefix = f"\\textbf{{{latex_escape(q.number)}.}}\\ " if q.number else ""
        if q.score is not None:
            prefix += f"\\textit{{（{_format_score(q.score)} 分）}}\\ "
        parts = [f"{hang}{prefix}{rich_doc_to_latex(q.stem, image_path)}\n"]
        if q.options:
            parts.append(self._render_options(q.options, q.option_columns, image_path, indent=bool(q.number)))
        inline = self._render_inline_fields(q.answer, q.thinking, q.analysis, q.summary, q.options, image_path)
        if inline:
            parts.append(inline)
        return "\n".join(parts)

    def _render_options(
        self, options: list[ExportOption], columns: int, image_path: ImagePathFn, indent: bool = False,
    ) -> str:
        columns = max(1, columns)
        lead = f"\\hspace*{{{_NUMBER_INDENT}}}" if indent else ""
        items = [
            f"\\noindent {lead}{latex_escape(opt.label)}.\\ {rich_doc_to_latex(opt.content, image_path)}"
            for opt in options
        ]
        if columns <= 1:
            return "\n\n".join(items) + "\n"
        body = "\n\n".join(items)
        return f"\\begin{{multicols}}{{{columns}}}\n{body}\n\\end{{multicols}}\n"

    def _render_question_details(self, node: ExportQuestionDetailsNode, image_path: ImagePathFn) -> str:
        label = "答案汇总（此前题目）" if node.scope == "before" else "答案汇总（全篇）"
        parts = [f"\\textbf{{{label}}}\n"]
        for child in node.children:
            if isinstance(child, ExportHeadingNode):
                parts.append(self._render_heading(child, image_path))
            elif isinstance(child, ExportRichTextNode):
                parts.append(rich_doc_to_latex(child.content, image_path) + "\n")
            elif isinstance(child, ExportAnswerEntry):
                parts.append(self._render_answer_entry(child, image_path))
        return "\n".join(parts)

    def _render_answer_entry(self, entry: ExportAnswerEntry, image_path: ImagePathFn) -> str:
        parts = [f"\\textbf{{{latex_escape(entry.number)}.}}\n"] if entry.number else []
        inline = self._render_inline_fields(
            entry.answer, entry.thinking, entry.analysis, entry.summary, entry.options, image_path
        )
        if inline:
            parts.append(inline)
        return "\n".join(parts)

    # --- 内联答案/思路/解析/小结 ------------------------------------------ #
    def _render_inline_fields(
        self,
        answer: Any,
        thinking: RichDoc,
        analysis: RichDoc,
        summary: RichDoc,
        options: list[ExportOption],
        image_path: ImagePathFn,
    ) -> str:
        out: list[str] = []
        if answer is not None:
            ans_tex = rich_inline_to_latex(answer_spec_to_inline(answer, options), image_path)
            out.append(f"\\par\\textbf{{【答案】}}{ans_tex}")
        for value, label in zip((thinking, analysis, summary), (l for _, l in _LABELS)):
            if value:
                out.append(f"\\par\\textbf{{{label}}}{rich_doc_to_latex(value, image_path)}")
        return "\n".join(out)
