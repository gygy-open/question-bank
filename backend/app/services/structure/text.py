"""题干纯文本快照:拆解的输入,也是条件 / 设问原文区间(span)的坐标系。

与 ``rich_doc_to_plain_text`` 的区别:公式保留 ``$...$`` 定界符。这样 AI 能分清哪里
是公式,前端也能在快照上直接渲染公式并高亮区间。快照一旦写进 ``struct_runs``
就不再变化;题目之后被编辑,拆解显示为过期,而不是让 span 悄悄错位。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.question_content import parse_json_field

# 图片、音频、填空位在文本里的占位符(中性写法,不随界面语言变化)。
IMAGE_PLACEHOLDER = "[image]"
AUDIO_PLACEHOLDER = "[audio]"
BLANK_PLACEHOLDER = "____"

# 这些节点结束时换行。
_BLOCK_TYPES = {"paragraph", "heading", "blockMath", "listItem", "tableRow", "blockquote"}


def rich_doc_to_stem_text(doc: Any) -> str:
    """RichDoc(dict 或 JSON 字符串)→ 题干纯文本;空 → ""。"""
    doc = parse_json_field(doc)
    if not isinstance(doc, dict):
        return str(doc or "").strip()
    return _collapse(_node_text(doc))


def build_stem_text(content: Any, options: Any = None) -> str:
    """题干 + 选项拼成一段文本:选项每个一行,形如 ``A. 内容``。"""
    parts = [rich_doc_to_stem_text(content)]
    for label, text in _option_lines(options):
        parts.append(f"{label}. {text}" if label else text)
    return "\n".join(p for p in parts if p)


# region 内部实现

def _option_lines(options: Any) -> List[tuple]:
    """选项 → [(label, text)]。兼容新版 RichDoc 选项与旧版 markdown 字符串选项。"""
    options = parse_json_field(options)
    lines: List[tuple] = []
    if not isinstance(options, list):
        return lines
    for index, option in enumerate(options):
        if isinstance(option, dict):
            label = str(option.get("label") or chr(ord("A") + index))
            body = option.get("content")
            text = rich_doc_to_stem_text(body) if isinstance(body, (dict, str)) and body else ""
        else:
            label, text = chr(ord("A") + index), str(option)
        lines.append((label, text))
    return lines


def _node_text(node: Dict[str, Any]) -> str:
    """递归取一个节点的文本。"""
    node_type = node.get("type")
    attrs: Dict[str, Any] = node.get("attrs") or {}
    if node_type == "text":
        return str(node.get("text", ""))
    if node_type == "inlineMath":
        return f"${attrs.get('latex', '')}$"
    if node_type == "blockMath":
        return f"$${attrs.get('latex', '')}$$\n"
    if node_type == "image":
        return IMAGE_PLACEHOLDER
    if node_type == "audio":
        return AUDIO_PLACEHOLDER
    if node_type == "blank":
        return BLANK_PLACEHOLDER
    if node_type == "hardBreak":
        return "\n"
    if node_type == "tableCell" or node_type == "tableHeader":
        return _node_children(node).strip() + " | "
    inner = _node_children(node)
    if node_type in _BLOCK_TYPES:
        return inner.rstrip(" |") + "\n" if node_type == "tableRow" else inner + "\n"
    return inner


def _node_children(node: Dict[str, Any]) -> str:
    return "".join(_node_text(child) for child in node.get("content") or [] if isinstance(child, dict))


def _collapse(text: str) -> str:
    """去掉行尾空白与多余空行,保持文本紧凑、span 稳定。"""
    lines = [line.rstrip() for line in text.split("\n")]
    out: List[str] = []
    for line in lines:
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    return "\n".join(out).strip()

# endregion


def stimulus_text(content: Any) -> Optional[str]:
    """材料正文的纯文本快照(与题干同一规则)。"""
    text = rich_doc_to_stem_text(content)
    return text or None
