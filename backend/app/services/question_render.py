"""题目 v2 内容的运行时渲染助手(ORM 消费侧统一入口)。

职责:
- `rich_doc_to_markdown`:把 RichDoc 保真转回 Markdown(供 Paper 导出走 Pandoc/Markdown 路径)。
- `answer_spec_to_plain_text` / `answer_spec_to_markdown`:把 AnswerSpec 渲染为人类可读文本,
  选择题显示 label、判断题显示 对/错、填空连接 accept、解答引用参考、legacy 输出原文。

设计约束:
- 只依赖原生 dict/list + `question_content(_v1)` 的解析/纯文本助手,不引入 pydantic schema,避免循环。
- 任何未知/未来节点都不得抛异常:优先递归 content,否则退化为纯文本,绝不丢字符。
- 送给模型 / Pandoc 的一律是渲染结果,绝不是 JSON 原文。
"""

from __future__ import annotations

import math
from typing import Any, Optional

from app.services.question_content import parse_json_field
from app.services.question_content_v1 import rich_doc_to_plain_text

__all__ = [
    "rich_doc_to_markdown",
    "rich_doc_to_plain_text",
    "answer_spec_to_plain_text",
    "answer_spec_to_markdown",
]


# --------------------------------------------------------------------------- #
# RichDoc → Markdown(保真)
# --------------------------------------------------------------------------- #
def rich_doc_to_markdown(doc: Any) -> str:
    """把 RichDoc(对象或 ORM JSON 字符串)转回 Markdown;空 → ""。"""
    doc = parse_json_field(doc)
    if not doc or not isinstance(doc, dict):
        return ""
    md = _blocks_to_md(doc.get("content") or [])
    return md.strip("\n")


def _blocks_to_md(nodes: list[Any]) -> str:
    parts: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        parts.append(_block_to_md(node))
    return "\n\n".join(p for p in parts if p != "")


def _block_to_md(node: dict[str, Any]) -> str:
    t = node.get("type")

    if t == "paragraph":
        return _inline_to_md(node.get("content") or [])

    if t == "blockMath":
        latex = (node.get("attrs") or {}).get("latex", "")
        return f"$$\n{latex}\n$$"

    if t in ("bulletList", "orderedList"):
        ordered = t == "orderedList"
        lines: list[str] = []
        for i, item in enumerate(node.get("content") or []):
            if not isinstance(item, dict):
                continue
            inner = _blocks_to_md(item.get("content") or [])
            marker = f"{i + 1}." if ordered else "-"
            first = True
            for raw_line in inner.split("\n"):
                prefix = f"{marker} " if first else "  "
                lines.append(f"{prefix}{raw_line}" if raw_line else prefix.rstrip())
                first = False
        return "\n".join(lines)

    if t == "image":
        return _image_md(node)

    if t == "table":
        return _table_to_md(node)

    # 未知/未来块节点:优先递归 content,否则退化为纯文本,绝不抛异常。
    if node.get("content"):
        return _blocks_to_md(node.get("content") or [])
    text = node.get("text")
    return str(text) if text else ""


def _inline_to_md(nodes: list[Any]) -> str:
    out: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        out.append(_inline_node_to_md(node))
    return "".join(out)


def _inline_node_to_md(node: dict[str, Any]) -> str:
    t = node.get("type")

    if t == "text":
        return _apply_marks(node.get("text", ""), node.get("marks") or [])

    if t == "inlineMath":
        latex = (node.get("attrs") or {}).get("latex", "")
        return f"${latex}$"

    if t == "hardBreak":
        return "  \n"

    if t == "image":
        return _image_md(node)

    if t == "blank":
        # 填空占位:渲染为可见下划线,保留题干可读性。
        return "____"

    # 未知/未来行内节点:递归 content 或退化为文本。
    if node.get("content"):
        return _inline_to_md(node.get("content") or [])
    text = node.get("text")
    return str(text) if text else ""


def _apply_marks(text: str, marks: list[Any]) -> str:
    if not text:
        return text
    mark_types = {m.get("type") for m in marks if isinstance(m, dict)}
    # 由内到外包裹:上/下标用原始 HTML(Pandoc 可解析),粗体/斜体用 Markdown。
    if "subscript" in mark_types:
        text = f"<sub>{text}</sub>"
    if "superscript" in mark_types:
        text = f"<sup>{text}</sup>"
    if "bold" in mark_types:
        text = f"**{text}**"
    if "italic" in mark_types:
        text = f"*{text}*"
    return text


def _image_md(node: dict[str, Any]) -> str:
    attrs = node.get("attrs") or {}
    src = str(attrs.get("src", ""))
    alt = str(attrs.get("alt", "") or "")
    image = f"![{alt}]({src})"
    dimensions: list[str] = []
    for name in ("width", "height"):
        value = attrs.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        px = float(value)
        if not math.isfinite(px) or px <= 0:
            continue
        inches = f"{px / 96:.4f}".rstrip("0").rstrip(".")
        dimensions.append(f'{name}="{inches}in"')
    if dimensions:
        return f"{image}{{{' '.join(dimensions)}}}"
    return image


def _table_to_md(node: dict[str, Any]) -> str:
    rows: list[list[str]] = []
    for row in node.get("content") or []:
        if not isinstance(row, dict) or row.get("type") != "tableRow":
            continue
        cells: list[str] = []
        for cell in row.get("content") or []:
            if not isinstance(cell, dict):
                continue
            text = _blocks_to_md(cell.get("content") or []).replace("\n", " ").strip()
            cells.append(text)
        rows.append(cells)
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header = rows[0]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for r in rows[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# AnswerSpec → 人类可读
# --------------------------------------------------------------------------- #
def answer_spec_to_plain_text(answer: Any, options: Any = None) -> str:
    """把 AnswerSpec 渲染为纯文本(用于模型上下文 / 检索,绝不送 JSON 原文)。"""
    return _render_answer(answer, options, rich_doc_to_plain_text, join_sep="，")


def answer_spec_to_markdown(answer: Any, options: Any = None) -> str:
    """把 AnswerSpec 渲染为 Markdown(用于 Paper 导出,保留数学/富文本)。"""
    return _render_answer(answer, options, rich_doc_to_markdown, join_sep="，")


def _option_label_map(options: Any) -> dict[str, str]:
    options = parse_json_field(options) or []
    mapping: dict[str, str] = {}
    if isinstance(options, list):
        for opt in options:
            if isinstance(opt, dict):
                oid = str(opt.get("id", ""))
                if oid:
                    mapping[oid] = str(opt.get("label", "") or oid)
    return mapping


def _render_answer(answer: Any, options: Any, render, join_sep: str) -> str:
    ans = parse_json_field(answer)
    if not ans or not isinstance(ans, dict):
        return ""
    kind = ans.get("kind")
    labels = _option_label_map(options)

    if kind == "single_choice":
        correct = str(ans.get("correct", ""))
        return labels.get(correct, correct)

    if kind == "multiple_choice":
        return join_sep.join(labels.get(str(c), str(c)) for c in ans.get("correct") or [])

    if kind == "true_false":
        return "对" if ans.get("correct") else "错"

    if kind == "fill_in_the_blank":
        parts: list[str] = []
        for blank in ans.get("blanks") or []:
            if not isinstance(blank, dict):
                continue
            accept = [render(a) for a in (blank.get("accept") or [])]
            accept = [a for a in accept if a]
            parts.append(" 或 ".join(accept))
        return "；".join(p for p in parts if p)

    if kind == "free_response":
        return render(ans.get("reference"))

    if kind == "legacy_unresolved":
        return render(ans.get("raw"))

    return ""
