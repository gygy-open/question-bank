"""AnswerSpec → 行内 RichDoc 节点列表(供各格式渲染器统一消费,保留公式)。

选择/判断渲染为 label / 对错文本;填空/解答把内部 RichDoc 拍平成行内节点,
其中 blockMath 降级为 inlineMath,text/inlineMath 原样保留,绝不丢公式。
"""

from __future__ import annotations

from typing import Any, Optional

from app.services.exporting.contracts import ExportOption
from app.services.question_content import parse_json_field

InlineNode = dict[str, Any]


def _text(s: str) -> InlineNode:
    return {"type": "text", "text": s}


def _label_map(options: list[ExportOption]) -> dict[str, str]:
    return {o.id: (o.label or o.id) for o in options if o.id}


def _flatten_doc_inline(doc: Any) -> list[InlineNode]:
    """把一个 RichDoc(或 JSON 字符串)拍平成行内节点序列。"""
    doc = parse_json_field(doc)
    if not isinstance(doc, dict):
        return []
    out: list[InlineNode] = []
    _flatten_nodes(doc.get("content") or [], out, first=[True])
    return out


def _flatten_nodes(nodes: list[Any], out: list[InlineNode], first: list[bool]) -> None:
    for node in nodes:
        if not isinstance(node, dict):
            continue
        t = node.get("type")
        if t in ("text", "inlineMath", "hardBreak", "image", "blank"):
            out.append(node)
        elif t == "blockMath":
            out.append({"type": "inlineMath", "attrs": {"latex": (node.get("attrs") or {}).get("latex", "")}})
        elif t == "paragraph":
            if not first[0]:
                out.append(_text(" "))
            first[0] = False
            _flatten_nodes(node.get("content") or [], out, first)
        elif node.get("content"):
            _flatten_nodes(node.get("content") or [], out, first)
        elif node.get("text"):
            out.append(_text(str(node.get("text"))))


def _join(fragments: list[list[InlineNode]], sep: str) -> list[InlineNode]:
    out: list[InlineNode] = []
    for i, frag in enumerate(fragments):
        if i:
            out.append(_text(sep))
        out.extend(frag)
    return out


def answer_spec_to_inline(answer: Any, options: list[ExportOption]) -> list[InlineNode]:
    ans = parse_json_field(answer)
    if not isinstance(ans, dict):
        return []
    kind = ans.get("kind")
    labels = _label_map(options)

    if kind == "single_choice":
        correct = str(ans.get("correct", ""))
        return [_text(labels.get(correct, correct))]

    if kind == "multiple_choice":
        text = "，".join(labels.get(str(c), str(c)) for c in ans.get("correct") or [])
        return [_text(text)]

    if kind == "true_false":
        return [_text("对" if ans.get("correct") else "错")]

    if kind == "fill_in_the_blank":
        blank_frags: list[list[InlineNode]] = []
        for blank in ans.get("blanks") or []:
            if not isinstance(blank, dict):
                continue
            accepts = [_flatten_doc_inline(a) for a in (blank.get("accept") or [])]
            accepts = [a for a in accepts if a]
            blank_frags.append(_join(accepts, " 或 "))
        return _join([f for f in blank_frags if f], "；")

    if kind == "free_response":
        return _flatten_doc_inline(ans.get("reference"))

    if kind == "legacy_unresolved":
        return _flatten_doc_inline(ans.get("raw"))

    return []
