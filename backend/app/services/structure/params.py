"""参数槽(规格 §12.3 N1)的定位与体检。纯函数,不读数据库。

参数挂在一条条件或设问上,值必须是题干原文中的一段。定位规则:

- 已给出区间(人工在面板中选中)时直接使用,只校验;
- 否则在所属条目的原文区间内找 ``value`` 的第 ``occurrence`` 次「独立」出现:数字前后
  不能紧挨数字、小数点,也不能是上下标(``x^2`` 里的 2 不是常数项 2);字母前后不能紧挨
  字母,也不能是 LaTeX 命令的一部分。

| 检查 | 级别 | 说明 |
| --- | --- | --- |
| ``param_not_found`` | error | 在所属条目的原文中找不到这个值 |
| ``param_value_mismatch`` | error | 区间处的原文与 ``value`` 不一致 |
| ``param_outside_owner`` | error | 区间不在所属条目的原文区间内(或所属条目没有原文区间) |
| ``param_overlap`` | error | 两个参数的区间重叠 |
| ``param_owner_missing`` | error | 所属条目不存在 |
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .check import Issue

SLOT_KINDS = ("numeric", "symbolic", "point", "interval", "expression")


@dataclass
class DraftParam:
    """一个待落库的参数槽。``owner`` 为 element / ask,``owner_index`` 是条目下标。"""

    name: str
    value: str
    owner: str
    owner_index: int
    slot_kind: str = "numeric"
    span: Optional[Tuple[int, int]] = None
    occurrence: int = 1
    domain: Optional[Dict[str, Any]] = None
    domain_confirmed: bool = False
    replaceable: bool = True


# region 公共函数

def locate_value(stem: str, value: str, within: Tuple[int, int], occurrence: int = 1) -> Optional[Tuple[int, int]]:
    """在 ``stem[within]`` 中找 ``value`` 的第 ``occurrence`` 次出现,且必须是独立出现。

    模型给出的序号有时按全部出现计数(``4.5`` 里的 4 也算一次),有时只数独立出现:
    先按全部出现取,取到的不是独立出现时,再按独立出现的序号取。
    """
    if not value:
        return None
    start, end = within
    raw: List[Tuple[int, int]] = []
    position = stem.find(value, start)
    while position != -1 and position + len(value) <= end:
        raw.append((position, position + len(value)))
        position = stem.find(value, position + 1)
    index = max(occurrence, 1) - 1
    if index < len(raw) and _standalone(stem, *raw[index]):
        return raw[index]
    hits = [hit for hit in raw if _standalone(stem, *hit)]
    return hits[index] if index < len(hits) else None


def check_params(
    stem: str,
    params: Sequence[DraftParam],
    element_spans: Sequence[Optional[Tuple[int, int]]],
    ask_spans: Sequence[Optional[Tuple[int, int]]],
) -> List[Issue]:
    """定位并体检参数(把定位出的区间写回 ``param.span``),返回问题清单。"""
    issues: List[Issue] = []
    for index, param in enumerate(params):
        spans = element_spans if param.owner == "element" else ask_spans
        if not 0 <= param.owner_index < len(spans):
            issues.append(_issue("param_owner_missing", "Parameter belongs to a missing item", index, param.name))
            param.span = None
            continue
        owner_span = spans[param.owner_index]
        if param.span is None and owner_span is not None:
            param.span = locate_value(stem, param.value, owner_span, param.occurrence)
            if param.span is None:
                issues.append(_issue(
                    "param_not_found", "Parameter value is not found in its item", index, param.value
                ))
                continue
        if param.span is None:
            issues.append(_issue("param_outside_owner", "Parameter item has no source span", index, param.name))
            continue
        start, end = param.span
        if not (0 <= start < end <= len(stem)) or stem[start:end] != param.value:
            issues.append(_issue(
                "param_value_mismatch", "Parameter value differs from the stem text", index,
                stem[start:end] if 0 <= start < end <= len(stem) else "",
            ))
            continue
        if owner_span is None or start < owner_span[0] or end > owner_span[1]:
            issues.append(_issue("param_outside_owner", "Parameter lies outside its item", index, param.name))
    located = sorted(
        ((p.span, i) for i, p in enumerate(params) if p.span is not None), key=lambda item: item[0][0]
    )
    for (first, _), (second, index) in zip(located, located[1:]):
        if second[0] < first[1]:
            issues.append(_issue("param_overlap", "Parameters overlap", index, params[index].name))
    return issues


def parse_domain(raw: Any) -> Optional[Dict[str, Any]]:
    """取值范围:只保留认识的键,其余丢弃。"""
    if not isinstance(raw, dict):
        return None
    out: Dict[str, Any] = {}
    for key in ("min", "max"):
        if isinstance(raw.get(key), (int, float)) and not isinstance(raw.get(key), bool):
            out[key] = raw[key]
    if isinstance(raw.get("integer"), bool):
        out["integer"] = raw["integer"]
    for key in ("values", "exclude"):
        if isinstance(raw.get(key), list):
            out[key] = [str(v) for v in raw[key]][:50]
    if raw.get("note"):
        out["note"] = str(raw["note"])[:500]
    return out or None

# endregion


# region 内部实现

_COMMAND_TAIL_RE = re.compile(r"\\[A-Za-z]*$")


def _standalone(stem: str, start: int, end: int) -> bool:
    """``stem[start:end]`` 是否是独立的一个值,而不是更长的数 / 词 / 上下标 / 命令的一部分。"""
    first, last = stem[start], stem[end - 1]
    before = stem[start - 1] if start > 0 else ""
    after = stem[end] if end < len(stem) else ""
    if first.isdigit() or first == ".":
        if before and (before.isdigit() or before in ".^_"):
            return False
        if before == "{" and start >= 2 and stem[start - 2] in "^_":
            return False
    if first.isalpha() and before and (before.isalpha() or _COMMAND_TAIL_RE.search(stem[:start])):
        return False
    if last.isdigit() and after and (after.isdigit() or after == "."):
        return False
    if last.isalpha() and after and after.isalpha():
        return False
    return True


def _issue(code: str, message: str, index: int, detail: str) -> Issue:
    return Issue(code=code, severity="error", message=message, target="param", index=index, detail=detail)

# endregion

