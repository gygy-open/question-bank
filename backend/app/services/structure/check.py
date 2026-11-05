"""题干拆解的自动体检(纯文本,不调用模型、不读数据库)。

把题干拆成「条件 + 设问」后,审核成本主要花在看明显错误上;这些错误只看文本就能
判出来,在审核前先筛一遍,人只需要看报错的那几条。思路来自 PR #28,并修正了评审
中发现的问题:

- 设问符号检查先剥离 LaTeX 命令(``\\frac``、``\\left`` 里的字母不再冒充变量)
  与 sin、ln 这类函数名,再逐个字母取符号(数学里 ``ax`` 是 a 乘 x,两个都是变量);
- 同一段文字在原文出现多次时,按出现顺序依次定位,不会全部挤到第一处而被误判重复;
- 定位引文时容忍等价的 LaTeX 写法(``\\left``/``\\right``、``\\{``、导数撇号的不同写法);
- 选项标签(「选项 A」「从 A、B、C、D 中选」)与概率 / 期望 / 方差记号 P(…) E(…) D(…) 不算变量;
- 区间以拆解快照 ``stem_text`` 为准(见 ``text.py``)。

| 检查 | 级别 | 说明 |
| --- | --- | --- |
| ``empty`` | error | 条目内容为空 |
| ``span_not_found`` | error | 条目引用的原文在题干里找不到(常见于 AI 把原文「写顺」了) |
| ``duplicate`` | error | 两条条件说的是同一件事 |
| ``dangling_symbol`` | error | 设问引用的符号没有任何条件承载——最可靠的漏拆信号 |
| ``compound`` | warning | 一条条件可能塞了多个断言 |
| ``uncovered`` | info | 题干里没被任何条目覆盖的文字(``strict`` 时为 error) |

不判断「某条条件删掉后题目是否仍成立」——那需要真的去解题,留给人工审核。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

# 题干里不承载条件信息的套话。只收多字短语与少数单字连接词——单字收多了会把实义
# 内容一起吃掉,漏拆反而被判成通过。
STEM_FILLERS: Tuple[str, ...] = (
    "如图所示", "如图", "已知", "请判断", "请说明理由", "下列说法", "下列", "其中", "那么",
    "则", "若", "设", "求", "的是", "（ ）", "( )", "（）", "()",
)

_PUNCT_RE = re.compile(r"[\s，。；：、（）()【】\[\]《》〈〉“”‘’\"'？！!?,.;:…—－·~～|$]+")
_OPTION_LABEL_RE = re.compile(r"(?m)^\s*[A-H][.．、]\s*")
_BLANK_RE = re.compile(r"_{2,}")
# 一个条件里出现这些连接词,通常意味着它塞了两个独立断言。
_COMPOUND_RE = re.compile(r"并且|而且|(?<![而并])且(?![体])|另外")
# LaTeX 命令(\frac、\left、\mathrm ……)整体去掉,只留参数里的内容。
_LATEX_COMMAND_RE = re.compile(r"\\[A-Za-z]+")
# 坐标轴名称(x 轴、y 轴)不是变量。
_AXIS_RE = re.compile(r"[A-Za-z](?=\s*轴)")
# 引用选项标签不是变量:「选项 A」「A 选项」总是选项标签。
_OPTION_REF_RE = re.compile(
    r"选项\s*[A-H](?:\s*[、,，/和与及]\s*[A-H])*|(?<![A-Za-z])[A-H](?=\s*选项)"
)
# 「A、B、C、D」这样的字母序列只在设问谈论选项时才当作选项标签——几何里「A、B 两点」是变量。
_OPTION_SEQUENCE_RE = re.compile(r"(?<![A-Za-z])[A-H](?:\s*[、,，/]\s*[A-H])+(?![A-Za-z])")
_OPTION_CONTEXT_RE = re.compile(r"选项|下列|以下")
# 概率 P(…)、期望 E(…)、方差 D(…) 是运算记号,不是需要条件给出的变量。
_OPERATOR_RE = re.compile(r"(?<![A-Za-z])[PED](?=\s*\()")
# 不带反斜杠写出的常见函数名 / 运算名,整体去掉,不拆成字母。
_FUNCTION_WORD_RE = re.compile(
    r"arc(?:sin|cos|tan|cot)|sinh|cosh|tanh|sin|cos|tan|cot|sec|csc|log|lg|ln|exp|max|min|lim|det|gcd|lcm|mod"
)
# 宽松定位时忽略的排版命令(不改变数学含义)。
_LATEX_LAYOUT_RE = re.compile(r"\\(?:left|right|big|Big|bigg|Bigg|displaystyle|textstyle)(?![A-Za-z])\.?")
# 导数撇号的几种写法。
_PRIME_RE = re.compile(r"\\prime(?![A-Za-z])|\\?′")
# 符号:剥离命令与函数名之后的每一个拉丁字母(数学里相邻字母表示乘积)。
_SYMBOL_RE = re.compile(r"[A-Za-z]")
# 不需要由条件承载的符号:自然常数 e。
_SYMBOL_ALLOWLIST = frozenset({"e"})

# 两条条件内容相似度超过它即视为重复。
_DUP_TEXT_RATIO = 0.95
# 两条条件原文区间高度重合、且内容也较相似时,同样视为重复。
_DUP_SPAN_IOU = 0.7
_DUP_SPAN_TEXT_RATIO = 0.8


@dataclass(frozen=True)
class CheckItem:
    """一条待检查的条目(条件或设问)。

    :param content: 规范化后的表述。
    :param source: 它在题干里的原文引文;为空时用 ``content`` 去原文里找。
    :param start / end: 已知的原文区间(指向 stem_text);给出时优先使用。
    :param shared: 是否引用了材料拆解中的条件(共享条件不在本题干里,不做定位)。
    """

    content: str
    source: Optional[str] = None
    start: Optional[int] = None
    end: Optional[int] = None
    shared: bool = False


@dataclass(frozen=True)
class Issue:
    """一条体检结论。``target`` 为 element / ask / None(针对整个题干)。"""

    code: str
    severity: str
    message: str
    target: Optional[str] = None
    index: Optional[int] = None
    detail: str = ""


@dataclass
class Report:
    """体检报告。``spans`` 是定位出的原文区间,与输入一一对应(找不到为 None)。"""

    issues: List[Issue] = field(default_factory=list)
    coverage: float = 1.0
    residual: str = ""
    element_spans: List[Optional[Tuple[int, int]]] = field(default_factory=list)
    ask_spans: List[Optional[Tuple[int, int]]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """没有 error 级问题。"""
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def to_dict(self) -> Dict[str, Any]:
        """存进 ``struct_runs.check_report`` 的 JSON 结构。"""
        return {
            "ok": self.ok,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "coverage": round(self.coverage, 4),
            "residual": self.residual,
            "issues": [
                {
                    "code": i.code,
                    "severity": i.severity,
                    "target": i.target,
                    "index": i.index,
                    "message": i.message,
                    "detail": i.detail,
                }
                for i in self.issues
            ],
        }


# region 公共函数

def check_structure(
    stem: str,
    elements: Sequence[CheckItem],
    asks: Sequence[CheckItem] = (),
    *,
    shared_texts: Sequence[str] = (),
    strict: bool = False,
) -> Report:
    """体检一份拆解。

    :param stem: 题干纯文本快照。
    :param elements: 条件。
    :param asks: 设问。
    :param shared_texts: 引用的材料条件的文本——它们也能承载设问里的符号。
    :param strict: 为 True 时把「未覆盖的文字」也当作错误。
    """
    report = Report()
    _check_empty(report, elements, "element")
    _check_empty(report, asks, "ask")

    # 1) 定位原文区间:同一段引文出现多次时,按顺序依次占用后面的出现位置。
    cursor: Dict[str, int] = {}
    report.element_spans = [_resolve(stem, item, cursor) for item in elements]
    report.ask_spans = [_resolve(stem, item, cursor) for item in asks]
    for target, items, spans in (("element", elements, report.element_spans), ("ask", asks, report.ask_spans)):
        for index, (item, span) in enumerate(zip(items, spans)):
            if span is None and item.content.strip() and not item.shared:
                report.issues.append(Issue(
                    "span_not_found", "error",
                    "Cannot find the source text of this item in the stem",
                    target, index, item.source or item.content,
                ))

    # 2) 重复
    _check_duplicates(report, elements)

    # 3) 一条条件多个断言
    for index, item in enumerate(elements):
        matched = _COMPOUND_RE.search(item.content)
        if matched:
            report.issues.append(Issue(
                "compound", "warning",
                "This condition may contain more than one assertion; consider splitting it",
                "element", index, matched.group(0),
            ))

    # 4) 设问符号必须有条件承载
    carried = set()
    for item in elements:
        carried |= symbols_of(item.content) | symbols_of(item.source or "")
    for text in shared_texts:
        carried |= symbols_of(text)
    reported: set = set()
    for index, ask in enumerate(asks):
        for symbol in sorted(symbols_of(ask.content) - carried - _SYMBOL_ALLOWLIST):
            if symbol in reported:
                continue
            reported.add(symbol)
            report.issues.append(Issue(
                "dangling_symbol", "error",
                f"The ask uses symbol '{symbol}' but no condition defines it",
                "ask", index, symbol,
            ))

    # 5) 未覆盖的文字(只提示)
    covered = [False] * len(stem)
    for span in [*report.element_spans, *report.ask_spans]:
        if span:
            for position in range(span[0], span[1]):
                covered[position] = True
    residual = effective_text("".join(ch if not cov else "\n" for ch, cov in zip(stem, covered)))
    total = effective_text(stem)
    report.residual = residual
    report.coverage = 1.0 - len(residual) / len(total) if total else 1.0
    if residual:
        report.issues.append(Issue(
            "uncovered", "error" if strict else "info",
            "Some text in the stem is not covered by any item; check whether something was missed",
            None, None, residual,
        ))
    return report


def symbols_of(text: str) -> set:
    """文本里的符号(先剥离 LaTeX 命令、函数名与坐标轴名称,再逐个取字母)。"""
    stripped = _LATEX_COMMAND_RE.sub(" ", text or "")
    stripped = _FUNCTION_WORD_RE.sub(" ", stripped)
    stripped = _AXIS_RE.sub(" ", stripped)
    stripped = _OPTION_REF_RE.sub(" ", stripped)
    if _OPTION_CONTEXT_RE.search(stripped):
        stripped = _OPTION_SEQUENCE_RE.sub(" ", stripped)
    stripped = _OPERATOR_RE.sub(" ", stripped)
    return set(_SYMBOL_RE.findall(stripped))


def effective_text(text: str) -> str:
    """去掉标点、选项标签、填空位与题面套话,只留下实义文本。

    「未覆盖」按实义字符计算:标点和“已知”“求”这类套话不承载条件,算进去会让
    分母虚高,真有内容漏掉时覆盖率仍然很好看。
    """
    stripped = _OPTION_LABEL_RE.sub("", text or "")
    stripped = _BLANK_RE.sub("", stripped)
    for filler in STEM_FILLERS:
        stripped = stripped.replace(filler, "")
    return _PUNCT_RE.sub("", stripped)


def locate(stem: str, quote: str, *, after: int = 0) -> Optional[Tuple[int, int]]:
    """在题干里找引文,返回原文区间。

    先精确查找;找不到时忽略空白与 ``$`` 再找一次(AI 引文常在公式两侧多 / 少空格或
    定界符),并把位置映射回原文。``after`` 之后找不到时不回退——由调用方决定。
    """
    if not quote:
        return None
    index = stem.find(quote, after)
    if index >= 0:
        return index, index + len(quote)
    compact_stem, spans = _compact_with_positions(stem)
    compact_quote, _ = _compact_with_positions(quote)
    if not compact_quote:
        return None
    compact_after = next((i for i, span in enumerate(spans) if span[0] >= after), len(spans))
    found = compact_stem.find(compact_quote, compact_after)
    if found < 0:
        return None
    start, end = spans[found][0], spans[found + len(compact_quote) - 1][1]
    # 引文自带公式定界符时,区间把紧挨着的 $ 也包进来,高亮才完整。
    while quote.lstrip().startswith("$") and start > 0 and stem[start - 1] == "$":
        start -= 1
    while quote.rstrip().endswith("$") and end < len(stem) and stem[end] == "$":
        end += 1
    return start, end

# endregion


# region 内部实现

def _check_empty(report: Report, items: Sequence[CheckItem], target: str) -> None:
    for index, item in enumerate(items):
        if not item.content.strip():
            report.issues.append(Issue("empty", "error", "This item is empty", target, index))


def _resolve(stem: str, item: CheckItem, cursor: Dict[str, int]) -> Optional[Tuple[int, int]]:
    """确定条目的原文区间:给定区间优先,否则按引文(或内容)顺序查找。"""
    if item.shared:
        return None
    if item.start is not None and item.end is not None:
        if 0 <= item.start < item.end <= len(stem):
            return item.start, item.end
        return None
    quote = (item.source or item.content or "").strip()
    if not quote:
        return None
    span = locate(stem, quote, after=cursor.get(quote, 0))
    if span is None and cursor.get(quote):
        # 后面再没有这段文字:回到第一处(两条条件确实引用同一处原文)。
        span = locate(stem, quote)
    if span is not None:
        cursor[quote] = span[1]
    return span


def _check_duplicates(report: Report, items: Sequence[CheckItem]) -> None:
    normalized = [effective_text(item.content) or item.content for item in items]
    spans = report.element_spans
    for left in range(len(items)):
        for right in range(left + 1, len(items)):
            if not normalized[left] or not normalized[right]:
                continue
            ratio = SequenceMatcher(None, normalized[left], normalized[right]).ratio()
            span_a, span_b = spans[left], spans[right]
            same_span = bool(span_a and span_b and _iou(span_a, span_b) >= _DUP_SPAN_IOU)
            if ratio >= _DUP_TEXT_RATIO or (same_span and ratio >= _DUP_SPAN_TEXT_RATIO):
                report.issues.append(Issue(
                    "duplicate", "error",
                    f"Conditions {left + 1} and {right + 1} say the same thing",
                    "element", right, f"{ratio:.2f}",
                ))


def _iou(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    overlap = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return overlap / union if union > 0 else 0.0


def _compact_with_positions(text: str) -> Tuple[str, List[Tuple[int, int]]]:
    """规范化用于宽松匹配的文本,并记下每个保留字符在原文中的区间。

    规范化规则(两边同样处理,所以 AI 引文与题干写法不同但等价时也能对上):
    - 去掉空白与 ``$``;
    - 去掉只影响排版的命令 ``\\left`` ``\\right`` ``\\displaystyle`` 等;
    - ``\\{`` ``\\}`` 视为 ``{`` ``}``(集合括号的转义写法);
    - ``\\prime``、``′``、``\\′`` 都视为 ``'``(导数记号)。
    一个被映射的多字符记号只产出一个字符,其区间覆盖整个记号,便于把位置映射回原文。
    """
    chars: List[str] = []
    spans: List[Tuple[int, int]] = []
    position = 0
    length = len(text)
    while position < length:
        matched = _LATEX_LAYOUT_RE.match(text, position)
        if matched:
            position = matched.end()
            continue
        prime = _PRIME_RE.match(text, position)
        if prime:
            chars.append("'")
            spans.append((position, prime.end()))
            position = prime.end()
            continue
        ch = text[position]
        if ch == "\\" and position + 1 < length and text[position + 1] in "{}":
            chars.append(text[position + 1])
            spans.append((position, position + 2))
            position += 2
            continue
        if not (ch.isspace() or ch == "$"):
            chars.append(ch)
            spans.append((position, position + 1))
        position += 1
    return "".join(chars), spans

# endregion
