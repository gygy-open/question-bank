"""RichDoc → LaTeX 片段(直接遍历,替代旧的 MD→pandoc 双跳)。

- math 节点已带 latex,原样输出、不转义;text 节点的 LaTeX 特殊字符必须转义。
- 未知/未来节点绝不抛异常、绝不丢字符:优先递归 content,否则退化为转义文本。
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable, Optional

from app.services.question_content import parse_json_field

__all__ = ["rich_doc_to_latex", "rich_inline_to_latex", "latex_escape"]

ImagePathFn = Optional[Callable[[str], Optional[str]]]

_BLANK_WIDTH_MIN_EM = 2
_BLANK_WIDTH_MAX_EM = 30
_BLANK_WIDTH_DEFAULT_EM = 4

# 单次替换,避免注入命令里的 {} 被后续规则二次转义。
_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _ESCAPE_MAP))


def latex_escape(text: str) -> str:
    if not text:
        return ""
    return _ESCAPE_RE.sub(lambda m: _ESCAPE_MAP[m.group()], text)


def _blank_width_em(node: dict[str, Any]) -> float:
    value = (node.get("attrs") or {}).get("widthEm")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return _BLANK_WIDTH_DEFAULT_EM
    return min(_BLANK_WIDTH_MAX_EM, max(_BLANK_WIDTH_MIN_EM, float(value)))


def rich_doc_to_latex(doc: Any, image_path: ImagePathFn = None) -> str:
    """把 RichDoc(对象或 ORM JSON 字符串)转成 LaTeX 片段;空 → ""。"""
    doc = parse_json_field(doc)
    if not doc or not isinstance(doc, dict):
        return ""
    return _blocks(doc.get("content") or [], image_path).strip("\n")


def rich_inline_to_latex(nodes: list[Any], image_path: ImagePathFn = None) -> str:
    return _inline(nodes, image_path)


def _blocks(nodes: list[Any], image_path: ImagePathFn) -> str:
    parts = [_block(n, image_path) for n in nodes if isinstance(n, dict)]
    return "\n\n".join(p for p in parts if p != "")


def _block(node: dict[str, Any], image_path: ImagePathFn) -> str:
    t = node.get("type")

    if t == "paragraph":
        return _inline(node.get("content") or [], image_path)

    if t == "blockMath":
        latex = (node.get("attrs") or {}).get("latex", "")
        return f"\\[\n{latex}\n\\]"

    if t in ("bulletList", "orderedList"):
        env = "enumerate" if t == "orderedList" else "itemize"
        items = []
        for item in node.get("content") or []:
            if not isinstance(item, dict):
                continue
            inner = _blocks(item.get("content") or [], image_path)
            items.append(f"\\item {inner}")
        body = "\n".join(items)
        return f"\\begin{{{env}}}\n{body}\n\\end{{{env}}}"

    if t == "image":
        return _image(node, image_path)

    if t == "table":
        return _table(node, image_path)

    if t == "blockquote":
        return f"\\begin{{quote}}\n{_blocks(node.get('content') or [], image_path)}\n\\end{{quote}}"

    if t == "codeBlock":
        # verbatim 原样输出，不转义（内容不应含 \end{verbatim}）。
        return f"\\begin{{verbatim}}\n{_collect_text(node)}\n\\end{{verbatim}}"

    if t == "horizontalRule":
        return "\\begin{center}\\rule{0.9\\linewidth}{0.4pt}\\end{center}"

    # 未知/未来块:优先递归,否则退化为转义文本,绝不丢字符。
    if node.get("content"):
        return _blocks(node.get("content") or [], image_path)
    return latex_escape(str(node.get("text") or ""))


def _collect_text(node: dict[str, Any]) -> str:
    """收集块内文本（代码块用），hardBreak 视为换行。"""
    parts: list[str] = []
    for child in node.get("content") or []:
        if not isinstance(child, dict):
            continue
        if child.get("type") == "text":
            parts.append(str(child.get("text") or ""))
        elif child.get("type") == "hardBreak":
            parts.append("\n")
        else:
            parts.append(_collect_text(child))
    return "".join(parts)


def _inline(nodes: list[Any], image_path: ImagePathFn) -> str:
    return "".join(_inline_node(n, image_path) for n in nodes if isinstance(n, dict))


def _inline_node(node: dict[str, Any], image_path: ImagePathFn) -> str:
    t = node.get("type")

    if t == "text":
        return _apply_marks(latex_escape(node.get("text", "")), node.get("marks") or [])

    if t == "inlineMath":
        latex = (node.get("attrs") or {}).get("latex", "")
        return f"${latex}$"

    if t == "hardBreak":
        return "\\\\\n"

    if t == "image":
        return _image(node, image_path)

    if t == "blank":
        return f"\\underline{{\\hspace{{{_blank_width_em(node):g}em}}}}"

    if node.get("content"):
        return _inline(node.get("content") or [], image_path)
    return latex_escape(str(node.get("text") or ""))


def _apply_marks(text: str, marks: list[Any]) -> str:
    if not text:
        return text
    mark_types = {m.get("type") for m in marks if isinstance(m, dict)}
    # 由内到外包裹。
    if "subscript" in mark_types:
        text = f"\\textsubscript{{{text}}}"
    if "superscript" in mark_types:
        text = f"\\textsuperscript{{{text}}}"
    if "bold" in mark_types:
        text = f"\\textbf{{{text}}}"
    if "italic" in mark_types:
        text = f"\\textit{{{text}}}"
    return text


def _image(node: dict[str, Any], image_path: ImagePathFn) -> str:
    attrs = node.get("attrs") or {}
    src = str(attrs.get("src", ""))
    resolved = image_path(src) if (image_path and src) else None
    if not resolved:
        # 图片无法解析时退化为 alt 文本,不静默丢弃。
        alt = str(attrs.get("alt", "") or "")
        return latex_escape(alt)
    opts = ""
    width = attrs.get("width")
    if isinstance(width, (int, float)) and not isinstance(width, bool) and math.isfinite(float(width)) and width > 0:
        opts = f"[width={float(width) / 96:.4f}in]"
    return f"\\includegraphics{opts}{{{resolved}}}"


def _table(node: dict[str, Any], image_path: ImagePathFn) -> str:
    rows: list[list[str]] = []
    for row in node.get("content") or []:
        if not isinstance(row, dict) or row.get("type") != "tableRow":
            continue
        cells: list[str] = []
        for cell in row.get("content") or []:
            if not isinstance(cell, dict):
                continue
            cells.append(_blocks(cell.get("content") or [], image_path).replace("\n", " ").strip())
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    col_spec = "|" + "c|" * width
    lines = [f"\\begin{{tabular}}{{{col_spec}}}", "\\hline"]
    for r in rows:
        lines.append(" & ".join(r) + " \\\\")
        lines.append("\\hline")
    lines.append("\\end{tabular}")
    return "\n".join(lines)
