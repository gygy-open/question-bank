"""题干拆成「元素」之后的自动体检。

把题干拆成原子元素（一条只说一件事），是后续检索、变式生成与命题复用的
前提。人工拆解最常见的两类错误是**漏拆**（题干里有实义内容没进任何元素）
和**重拆**（两条元素说同一件事）。这两类都能只靠文本判出来，既不需要解题
也不需要调模型。

第三类是「这条元素能不能删掉而题目仍然成立」——它必须真的删掉再解一遍题，
纯文本判不出来。本模块不假装能判，把它交给人工。

因此这里的定位是**审核前的筛子**，不是审核本身：机器只把明显有问题的挑
出来，人可以只看报错的那几条。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Sequence

#: 题干里不承载条件信息的套话。只收多字短语，单字（的／为／中／有）一律不
#: 收——收了会把实义内容一起吃掉，漏拆反而被判成通过。
STEM_FILLERS: tuple[str, ...] = (
    "如图所示",
    "如图",
    "已知",
    "请判断",
    "请说明理由",
    "其中",
    "下列",
    "那么",
    "求",
    "设",
)

_PUNCT_RE = re.compile(r"[\s，。；：、（）()【】\[\]《》〈〉“”‘’\"'？！!?,.;:…—－·~～]+")
_ORDINAL_RE = re.compile(r"^\s*(?:\d+\s*[．.、]|[（(]\s*\d+\s*[）)]|[①②③④⑤⑥])")
#: 一个元素里出现这些连接词，通常意味着它塞了两个独立断言。
_COMPOUND_RE = re.compile(r"且(?![体对应])|并且|同时|另外")

#: 两条元素的原文区间重合度超过它就认为是同一件事写了两遍。
_SPAN_DUP_IOU = 0.7
#: 两条元素没有区间时，退化为比文本。
_TEXT_DUP_RATIO = 0.95

#: 设问里引用的单字母符号。前后不能是字母，避免把 xOy、f(x) 里的连续标识符拆碎。
_SYMBOL_RE = re.compile(r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])")


@dataclass(frozen=True)
class Element:
    """一条元素。

    :param text: 规范化后的表述，一条只说一件事。
    :param start: 该元素在题干原文中的起始字符下标；未知时为 None。
    :param end: 结束下标（不含）；未知时为 None。
    :param role: 可选的角色标记。``"ask"`` 表示这一条是设问而不是条件——
        设问里的符号本来就不需要由条件承载，做符号检查时要排除掉。
    """

    text: str
    start: int | None = None
    end: int | None = None
    role: str | None = None

    def __post_init__(self) -> None:
        if (self.start is None) != (self.end is None):
            raise ValueError("start 与 end 必须同时给出或同时省略")


@dataclass(frozen=True)
class Issue:
    """一条体检结论。

    ``severity`` 为 ``error`` 时说明这条拆解基本不能采纳；``warning`` 只是提醒，
    可能是作者有意为之（例如把一组同类型条件放进一条元素）。
    """

    code: str
    message: str
    severity: str = "error"
    index: int | None = None
    detail: str = ""


@dataclass(frozen=True)
class Report:
    """体检报告。"""

    issues: tuple[Issue, ...]
    coverage: float
    residual: str

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity == "error")

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "coverage": round(self.coverage, 4),
            "residual": self.residual,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity,
                    "index": i.index,
                    "message": i.message,
                    "detail": i.detail,
                }
                for i in self.issues
            ],
        }


def effective_text(text: str) -> str:
    """去掉标点、题号与题面套话，只留下实义文本。

    漏拆与否是按「实义字符」算的：题干里那些标点和“如图”“已知”不承载条件，
    把它们算进覆盖率会让分母虚高，真有内容漏掉时覆盖率仍然很好看。
    """
    stripped = text
    for filler in STEM_FILLERS:
        stripped = stripped.replace(filler, "")
    # 先剥题号再去标点：反过来会把「（2）」先变成「2」，题号就认不出来了。
    stripped = "\n".join(_ORDINAL_RE.sub("", line) for line in stripped.split("\n"))
    stripped = _PUNCT_RE.sub("", stripped)
    return stripped.strip()


def _resolve_span(stem: str, element: Element) -> tuple[int, int] | None:
    """定位元素在原文里的区间。给定区间优先，否则按文本查找。"""
    if element.start is not None and element.end is not None:
        start, end = element.start, element.end
        if 0 <= start < end <= len(stem):
            return start, end
        return None
    if not element.text:
        return None
    index = stem.find(element.text)
    if index < 0:
        return None
    return index, index + len(element.text)


def _iou(a: tuple[int, int], b: tuple[int, int]) -> float:
    """两段区间的交并比。"""
    overlap = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return overlap / union if union > 0 else 0.0


def check_structure(
    stem: str,
    elements: Sequence[Element | str],
    *,
    asks: Sequence[str] = (),
    strict: bool = False,
) -> Report:
    """体检一份元素拆解。

    严格判定的有四类：元素为空、元素在原文里找不到依据、两条元素重复、
    设问引用了没有元素承载的符号。「残差」只给提示——纯文本判不准，详见上方注释。

    :param asks: 设问文本。给出后会检查每条设问引用的符号是否被某条元素承载，
        这是**唯一可靠的漏拆信号**：漏掉一个含参式子时，设问里的符号就悬空了。
    :param strict: 为 True 时把残差也当作错误，适合批量导入这种要求完备的场景。

    >>> check_structure("已知 f(x)=x^3+ax+2 有三个零点。", ["f(x)=x^3+ax+2", "有三个零点"]).ok
    True
    """
    normalized: list[Element] = [
        item if isinstance(item, Element) else Element(text=item) for item in elements
    ]
    issues: list[Issue] = []

    # 1) 空元素
    for index, element in enumerate(normalized):
        if not element.text.strip():
            issues.append(Issue("empty", "第 %d 条元素是空的" % (index + 1), index=index))

    # 2) 定位并标记覆盖区间
    spans: list[tuple[int, int] | None] = []
    mask = [False] * len(stem)
    for index, element in enumerate(normalized):
        if not element.text.strip():
            spans.append(None)
            continue
        span = _resolve_span(stem, element)
        spans.append(span)
        if span is None:
            issues.append(
                Issue(
                    "span_not_found",
                    "第 %d 条元素在题干里找不到对应原文" % (index + 1),
                    index=index,
                    detail=element.text,
                )
            )
            continue
        for position in range(span[0], span[1]):
            mask[position] = True

    # 3) 漏拆：原文里没被任何元素覆盖的实义文本
    #
    # 这一项**不自动判对错**。原因很实在：题面里大量文字不承载可分离的条件
    # （“在平面直角坐标系中”“已知函数”“与 x 轴交于点”），它们不该进任何
    # 元素，但会被算成“没被覆盖”；反过来，真漏掉一条条件时残差常常只是几个
    # 数字，覆盖率看着仍然很高。两个方向都不准，所以这里只把残差摆出来给人看。
    #
    # 需要机器拍板的场景（例如批量导入必须完备）传 strict=True，此时残差非空
    # 即判为 error。
    residual = effective_text(
        "".join(char for char, covered in zip(stem, mask) if not covered)
    )
    stem_effective = effective_text(stem)
    if stem_effective:
        coverage = 1.0 - len(residual) / len(stem_effective)
    else:
        coverage = 1.0
    if residual:
        issues.append(
            Issue(
                "uncovered",
                "题干有内容没被任何元素覆盖，请人工确认是否漏拆",
                severity="error" if strict else "info",
                detail=residual,
            )
        )

    # 4) 重拆：两条元素指向同一段原文，或文本几乎一样
    for left in range(len(normalized)):
        for right in range(left + 1, len(normalized)):
            span_a, span_b = spans[left], spans[right]
            if span_a and span_b:
                score = _iou(span_a, span_b)
                if score >= _SPAN_DUP_IOU:
                    issues.append(
                        Issue(
                            "duplicate",
                            "第 %d、%d 条元素覆盖同一段原文" % (left + 1, right + 1),
                            index=right,
                            detail="重合度 %.2f" % score,
                        )
                    )
                continue
            ratio = SequenceMatcher(None, normalized[left].text, normalized[right].text).ratio()
            if ratio >= _TEXT_DUP_RATIO:
                issues.append(
                    Issue(
                        "duplicate",
                        "第 %d、%d 条元素文本几乎相同" % (left + 1, right + 1),
                        index=right,
                        detail="相似度 %.2f" % ratio,
                    )
                )

    # 5) 一条元素塞了多个断言
    for index, element in enumerate(normalized):
        matched = _COMPOUND_RE.search(element.text)
        if matched:
            issues.append(
                Issue(
                    "compound",
                    "第 %d 条元素可能含多个断言，考虑拆开" % (index + 1),
                    severity="warning",
                    index=index,
                    detail="命中连接词「%s」：%s" % (matched.group(0), element.text),
                )
            )

    # 6) 设问引用的符号必须有元素承载
    #
    # 这是唯一可靠的漏拆信号。漏掉一条含参条件时，残差往往只剩几个数字、覆盖率
    # 看着仍然很高；但设问里“求 a 的取值范围”的那个 a 会彻底悬空，一查就出。
    if asks:
        joined = "".join(item.text for item in normalized if item.role != "ask")
        reported: set[str] = set()
        for ask in asks:
            for symbol in _SYMBOL_RE.findall(ask):
                if symbol in reported or symbol in joined:
                    continue
                reported.add(symbol)
                issues.append(
                    Issue(
                        "dangling_symbol",
                        "设问引用了符号「%s」，但没有元素包含它" % symbol,
                        detail=ask,
                    )
                )

    return Report(issues=tuple(issues), coverage=coverage, residual=residual)


__all__ = [
    "Element",
    "Issue",
    "Report",
    "STEM_FILLERS",
    "check_structure",
    "effective_text",
]
