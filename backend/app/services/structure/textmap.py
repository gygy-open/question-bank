"""题干快照 ``stem_text`` ↔ RichDoc 的位置映射,用于按原文区间改写题目(参数槽变式)。

``text.build_stem_text`` 把题干与选项拼成一段纯文本,中间加入了定界符(``$``)、
换行、选项标签、占位符,并做了行尾空白与空行的折叠。这里用同一套规则逐字符重建
这段文本,同时记下每个字符来自哪个节点的哪个位置:

- 文本节点的字符 → (节点, ``text``, 下标);
- 公式节点的 LaTeX 字符 → (节点, ``latex``, 下标);
- 旧版字符串选项的字符 → (选项列表, 下标, 字符串内下标);
- 其余(定界符、换行、选项标签、占位符)→ 没有来源,不能被替换。

替换时按区间从后往前改写节点里的字符串,因此多处替换互不影响;区间跨越多个节点
或落在没有来源的字符上时拒绝替换(``UnmappableSpan``),绝不做全文字符串匹配——
否则把 ``2`` 换成 ``5`` 会连 ``x^2`` 一起改掉。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.question_content import parse_json_field

from .text import AUDIO_PLACEHOLDER, BLANK_PLACEHOLDER, IMAGE_PLACEHOLDER, _BLOCK_TYPES, build_stem_text

# 字符来源:(容器, 键, 下标)。容器是 RichDoc 中的节点 dict(键为 "text")、节点的 attrs
# dict(键为 "latex"),或旧版选项列表(键为选项下标)。
_Ref = Optional[Tuple[Any, Any, int]]


class UnmappableSpan(ValueError):
    """区间不能映射回题目内容(跨节点、落在定界符 / 标签上,或题目已被修改)。"""


@dataclass
class Replacement:
    """把 stem_text 的 [start, end) 替换为 ``text``。"""

    start: int
    end: int
    text: str


@dataclass
class _Chars:
    """逐字符的文本与来源。"""

    chars: List[str]
    refs: List[_Ref]

    def add(self, text: str, ref_of=None) -> None:
        for index, char in enumerate(text):
            self.chars.append(char)
            self.refs.append(ref_of(index) if ref_of else None)

    def extend(self, other: "_Chars") -> None:
        self.chars.extend(other.chars)
        self.refs.extend(other.refs)

    @property
    def text(self) -> str:
        return "".join(self.chars)


# region 公共函数

def apply_replacements(
    content: Any, options: Any, stem_text: str, replacements: Sequence[Replacement]
) -> Tuple[Any, Any]:
    """在题干 / 选项的副本上按区间替换,返回 (新题干, 新选项)。原对象不被修改。

    :param stem_text: 拆解快照里的题干文本;必须与当前内容重建出的文本一致,否则说明
        题目在拆解之后被改过,区间已不可信。
    :raises UnmappableSpan: 文本不一致、区间重叠或不能映射回单个节点。
    """
    content = copy.deepcopy(parse_json_field(content))
    options = copy.deepcopy(parse_json_field(options))
    mapped = _map_stem(content, options)
    if mapped.text != stem_text or mapped.text != build_stem_text(content, options):
        raise UnmappableSpan("The question changed after it was decomposed")

    ordered = sorted(replacements, key=lambda r: r.start, reverse=True)
    for later, earlier in zip(ordered, ordered[1:]):
        if earlier.end > later.start:
            raise UnmappableSpan("Replacement spans overlap")
    for item in ordered:
        container, key, first, last, text = _resolve(mapped, item)
        container[key] = container[key][:first] + text + container[key][last + 1:]
    return content, options


def stem_char_refs(content: Any, options: Any = None) -> List[bool]:
    """stem_text 中每个字符是否可替换(有来源)。供体检判断参数区间是否可用。"""
    mapped = _map_stem(copy.deepcopy(parse_json_field(content)), copy.deepcopy(parse_json_field(options)))
    return [ref is not None for ref in mapped.refs]

# endregion


# region 内部实现

def _resolve(mapped: _Chars, item: Replacement) -> Tuple[Any, Any, int, int, str]:
    """区间 → (容器, 键, 首字符下标, 末字符下标, 替换文本)。

    区间两端被 ``$`` 定界符包住时(参数值写成 ``$3$``),去掉定界符再映射,替换文本里
    对应的 ``$`` 也一并去掉。
    """
    start, end, text = item.start, item.end, item.text
    if not 0 <= start < end <= len(mapped.chars):
        raise UnmappableSpan("Replacement span is out of range")
    while start < end and mapped.refs[start] is None and mapped.chars[start] == "$":
        start += 1
        text = text[1:] if text.startswith("$") else text
    while end > start and mapped.refs[end - 1] is None and mapped.chars[end - 1] == "$":
        end -= 1
        text = text[:-1] if text.endswith("$") else text
    refs = mapped.refs[start:end]
    if not refs or any(ref is None for ref in refs):
        raise UnmappableSpan("Replacement span covers text that cannot be edited")
    container, key, first = refs[0]  # type: ignore[misc]
    for offset, ref in enumerate(refs):
        if ref[0] is not container or ref[1] != key or ref[2] != first + offset:  # type: ignore[index]
            raise UnmappableSpan("Replacement span crosses formatting or formula boundaries")
    return container, key, first, first + len(refs) - 1, text


def _map_stem(content: Any, options: Any) -> _Chars:
    """与 ``build_stem_text`` 相同的规则重建文本,并记录每个字符的来源。"""
    parts: List[_Chars] = [_map_doc(content)]
    if isinstance(options, list):
        for index, option in enumerate(options):
            if isinstance(option, dict):
                label = str(option.get("label") or chr(ord("A") + index))
                body = option.get("content")
                body = parse_json_field(body)
                if isinstance(body, dict):
                    option["content"] = body
                    text = _map_doc(body)
                elif isinstance(body, str) and body:
                    text = _Chars([], [])
                    text.add(body.strip())
                else:
                    text = _Chars([], [])
            else:
                label = chr(ord("A") + index)
                raw = str(option)
                text = _Chars([], [])
                text.add(raw, lambda i, idx=index: (options, idx, i))
            line = _Chars([], [])
            if label:
                line.add(f"{label}. ")
            line.extend(text)
            parts.append(line)
    out = _Chars([], [])
    for part in parts:
        if not part.chars:
            continue
        if out.chars:
            out.add("\n")
        out.extend(part)
    return out


def _map_doc(doc: Any) -> _Chars:
    if not isinstance(doc, dict):
        out = _Chars([], [])
        out.add(str(doc or "").strip())
        return out
    return _collapse(_map_node(doc))


def _map_node(node: Dict[str, Any]) -> _Chars:
    out = _Chars([], [])
    node_type = node.get("type")
    attrs = node.get("attrs")
    if node_type == "text":
        text = str(node.get("text", ""))
        node["text"] = text
        out.add(text, lambda i: (node, "text", i))
        return out
    if node_type in ("inlineMath", "blockMath"):
        if not isinstance(attrs, dict):
            attrs = {}
            node["attrs"] = attrs
        latex = str(attrs.get("latex", ""))
        attrs["latex"] = latex
        fence = "$" if node_type == "inlineMath" else "$$"
        out.add(fence)
        out.add(latex, lambda i: (attrs, "latex", i))
        out.add(fence + ("\n" if node_type == "blockMath" else ""))
        return out
    if node_type == "image":
        out.add(IMAGE_PLACEHOLDER)
        return out
    if node_type == "audio":
        out.add(AUDIO_PLACEHOLDER)
        return out
    if node_type == "blank":
        out.add(BLANK_PLACEHOLDER)
        return out
    if node_type == "hardBreak":
        out.add("\n")
        return out
    inner = _Chars([], [])
    for child in node.get("content") or []:
        if isinstance(child, dict):
            inner.extend(_map_node(child))
    if node_type in ("tableCell", "tableHeader"):
        inner = _strip(inner)
        inner.add(" | ")
        return inner
    if node_type in _BLOCK_TYPES:
        if node_type == "tableRow":
            inner = _rstrip(inner, " |")
        inner.add("\n")
    return inner


def _strip(text: _Chars, chars: Optional[str] = None) -> _Chars:
    return _lstrip(_rstrip(text, chars), chars)


def _rstrip(text: _Chars, chars: Optional[str] = None) -> _Chars:
    end = len(text.chars)
    while end and (text.chars[end - 1] in chars if chars else text.chars[end - 1].isspace()):
        end -= 1
    return _Chars(text.chars[:end], text.refs[:end])


def _lstrip(text: _Chars, chars: Optional[str] = None) -> _Chars:
    start = 0
    while start < len(text.chars) and (text.chars[start] in chars if chars else text.chars[start].isspace()):
        start += 1
    return _Chars(text.chars[start:], text.refs[start:])


def _collapse(text: _Chars) -> _Chars:
    """与 ``text._collapse`` 一致:行尾去空白、合并空行、首尾去空白。"""
    lines: List[_Chars] = []
    current = _Chars([], [])
    for char, ref in zip(text.chars, text.refs):
        if char == "\n":
            lines.append(current)
            current = _Chars([], [])
        else:
            current.chars.append(char)
            current.refs.append(ref)
    lines.append(current)
    kept: List[_Chars] = []
    for line in lines:
        line = _rstrip(line)
        if not line.chars and (not kept or not kept[-1].chars):
            continue
        kept.append(line)
    out = _Chars([], [])
    for index, line in enumerate(kept):
        if index:
            out.add("\n")
        out.extend(line)
    return _strip(out)

# endregion
