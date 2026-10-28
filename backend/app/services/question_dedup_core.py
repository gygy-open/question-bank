"""题目查重的纯函数部分:归一化、指纹、MinHash 分桶与相似度。

不碰数据库,便于单测;存储与查询见 `question_dedup.py`。设计见 docs/specs/question-dedup.md。

比对对象 = 题型 + 材料文本 + 题干 + 排序后的选项。答案/解析不参与:同一道题补了解析不是新题。
"""
from __future__ import annotations

import difflib
import hashlib
import json
import re
import struct
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional, Sequence, Tuple

# 归一化规则变更时递增,存量题目会被回填任务按版本重算。
DEDUP_VERSION = 1

SIMILAR_THRESHOLD = 0.90
# 归一化后短于此长度的题目只做精确比对:短文本的 n-gram 相似度没有区分度。
MIN_FUZZY_LENGTH = 8
SHINGLE_SIZE = 3
NUM_PERM = 64
BANDS = 16
ROWS = NUM_PERM // BANDS

_SEP_STIMULUS = "\u241e"  # 各部分之间的分隔符,归一化后的文本里不会出现
_SEP_OPTION = "\u241f"

# --------------------------------------------------------------------------- #
# RichDoc → 文本
# --------------------------------------------------------------------------- #
_BLOCK_TYPES = {"paragraph", "heading", "blockMath", "listItem", "tableCell", "tableHeader"}


def _parse(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _doc_text(node: Any) -> str:
    """RichDoc → 文本。公式保留 LaTeX(包上 $ 以便单独规范化),图片取资产 ID,填空取占位符。"""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_doc_text(n) for n in node)
    if not isinstance(node, dict):
        return ""
    t = node.get("type")
    attrs = node.get("attrs") or {}
    if t == "text":
        return node.get("text") or ""
    if t in ("inlineMath", "blockMath"):
        return f"${attrs.get('latex') or ''}$"
    if t == "image":
        asset = attrs.get("assetId")
        return f"[img:{asset}]" if asset else f"[img:{attrs.get('src') or ''}]"
    if t == "audio":
        return f"[audio:{attrs.get('assetId') or ''}]"
    if t == "blank":
        return "_"
    if t == "hardBreak":
        return " "
    inner = _doc_text(node.get("content") or [])
    return inner + " " if t in _BLOCK_TYPES else inner


# --------------------------------------------------------------------------- #
# 归一化
# --------------------------------------------------------------------------- #
# 中文标点 → 英文标点(NFKC 不处理的部分)
_PUNCT_MAP = str.maketrans({
    "，": ",", "、": ",", "。": ".", "．": ".", "：": ":", "；": ";", "？": "?", "！": "!",
    "（": "(", "）": ")", "【": "[", "】": "]", "〔": "(", "〕": ")", "「": '"', "」": '"',
    "『": '"', "』": '"', "“": '"', "”": '"', "‘": "'", "’": "'", "《": "<", "》": ">",
    "—": "-", "–": "-", "－": "-", "～": "~", "·": ".", "…": "...",
    "×": "\\times", "÷": "\\div", "≤": "\\le", "≥": "\\ge", "≠": "\\ne",
})

# 题号前缀:1.  1、 (1) ① 例1 第1题 一、
_NUMBER_PREFIX = re.compile(
    r"^\s*(?:"
    r"第?\d{1,3}[题小]?(?:\.(?!\d)|[,，、:：)）])|"  # 1.  1、 1) 第1题、(不吃小数 12.5)
    r"[(（]\d{1,3}[)）]|"                # (1) （1）
    r"[\u2460-\u2473]|"                # ①-⑳
    r"例\d{0,3}[.,、:]?|"              # 例1
    r"[一二三四五六七八九十]{1,3}[,、.]"  # 一、
    r")\s*"
)

# 不改变语义的排版命令
_LATEX_NOISE = re.compile(
    r"\\(?:left|right|displaystyle|textstyle|scriptstyle|limits|nolimits|big|Big|bigg|Bigg)(?![a-zA-Z])"
    r"|\\[,;:! ]|\\q?quad(?![a-zA-Z])|~"
)
_LATEX_ALIASES = (
    (re.compile(r"\\[dt]frac(?![a-zA-Z])"), r"\\frac"),
    (re.compile(r"\\leq(?![a-zA-Z])"), r"\\le"),
    (re.compile(r"\\geq(?![a-zA-Z])"), r"\\ge"),
    (re.compile(r"\\neq(?![a-zA-Z])"), r"\\ne"),
    (re.compile(r"\\(?:mathrm|text|textrm|operatorname)\{([^{}]*)\}"), r"\1"),
)


def _strip_bare_braces(latex: str) -> str:
    """去掉不承担参数作用的花括号:`( {2,p} )` → `(2,p)`、`x^{2}` → `x^2`。

    紧跟在命令名、`^`、`_` 或上一个参数后面的 `{` 是参数,保留(`\\frac{1}{23}` 与
    `\\frac{12}{3}` 必须可区分);单字符参数的花括号可去掉。
    """
    out: List[str] = []
    stack: List[Tuple[bool, int]] = []  # (是否保留, 在 out 中的位置)
    i = 0
    n = len(latex)
    while i < n:
        ch = latex[i]
        if ch == "\\" and i + 1 < n:
            j = i + 1
            if latex[j].isalpha():
                while j < n and latex[j].isalpha():
                    j += 1
            else:
                j += 1
            out.append(latex[i:j])
            i = j
            continue
        if ch == "{":
            prev = out[-1] if out else ""
            is_arg = prev.startswith("\\") and prev[1:].isalpha() or prev in ("^", "_", "}")
            stack.append((is_arg, len(out)))
            out.append("{")
            i += 1
            continue
        if ch == "}" and stack:
            is_arg, pos = stack.pop()
            inner = "".join(out[pos + 1:])
            if not is_arg or (len(inner) == 1 and out[pos - 1:pos] in (["^"], ["_"])):
                out[pos:] = [inner]
            else:
                out.append("}")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def normalize_latex(latex: str) -> str:
    s = _LATEX_NOISE.sub("", latex)
    for pattern, repl in _LATEX_ALIASES:
        s = pattern.sub(repl, s)
    # 命令名后紧跟字母时必须保留一个空格(`\sim B` 不能变成 `\simB`),其余空白全部去掉
    s = re.sub(
        r"(\\[a-zA-Z]+)\s+(?=[a-zA-Z])|\s+",
        lambda m: m.group(1) + " " if m.group(1) else "",
        s,
    )
    return _strip_bare_braces(s)


_MATH = re.compile(r"\$([^$]*)\$")
_BLANKS = re.compile(r"(?:_{2,}|\(\s*\)|\[\s*\]|_(?:_|\s)*)")


def normalize_text(text: str) -> str:
    """一段文本(可含 $LaTeX$)的归一化结果,空白全部去掉。"""
    if not text:
        return ""
    # 题号前缀在 NFKC 之前先去一次:NFKC 会把 ① 变成 1、把 （1） 变成 (1)
    text = _NUMBER_PREFIX.sub("", text.lstrip(), count=1)
    text = unicodedata.normalize("NFKC", text)
    # 公式先抽出来单独规范化,避免文本规则误伤 LaTeX
    parts: List[str] = []
    last = 0
    for m in _MATH.finditer(text):
        parts.append(_normalize_plain(text[last:m.start()]))
        parts.append(normalize_latex(m.group(1)))
        last = m.end()
    parts.append(_normalize_plain(text[last:]))
    joined = "".join(parts)
    joined = _NUMBER_PREFIX.sub("", joined, count=1)
    joined = _BLANKS.sub("_", joined)
    # 句末标点只是排版差异
    return joined.rstrip(".,;:!?")


def _normalize_plain(text: str) -> str:
    s = text.translate(_PUNCT_MAP).lower()
    return re.sub(r"\s+", "", s)


def normalize_doc(doc: Any) -> str:
    return normalize_text(_doc_text(_parse(doc)))


def normalize_options(options: Any) -> List[str]:
    """选项按内容排序:选项顺序打乱视为同一道题。label 不参与(A/B/C 只是位置)。"""
    options = _parse(options)
    if not isinstance(options, list):
        return []
    texts = []
    for opt in options:
        if isinstance(opt, dict):
            texts.append(normalize_doc(opt.get("content")))
        elif isinstance(opt, str):
            texts.append(normalize_text(opt))
    return sorted(t for t in texts if t)


# --------------------------------------------------------------------------- #
# 签名
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DedupKey:
    q_type: str
    text: str  # 拼接后的归一化文本(材料 + 题干 + 选项)
    stem_length: int

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(f"{self.q_type}\u241d{self.text}".encode("utf-8")).hexdigest()

    @property
    def fuzzy(self) -> bool:
        # 按题目本体(不含材料)判断:同一材料下的小题共享长材料,不能靠材料长度凑够模糊匹配门槛
        return len(split_stimulus(self.text)[1]) >= MIN_FUZZY_LENGTH

    @property
    def numeric_signature(self) -> Tuple[str, ...]:
        return numeric_signature(self.text)


def build_key(*, q_type: Any, content: Any, options: Any = None, stimulus_content: Any = None) -> DedupKey:
    q_type = getattr(q_type, "value", q_type) or ""
    stem = normalize_doc(content)
    parts = []
    if stimulus_content is not None:
        stimulus = normalize_doc(stimulus_content)
        if stimulus:
            parts.append(stimulus + _SEP_STIMULUS)
    parts.append(stem)
    opts = normalize_options(options)
    if opts:
        parts.append(_SEP_OPTION + _SEP_OPTION.join(opts))
    return DedupKey(q_type=str(q_type), text="".join(parts), stem_length=len(stem))


_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_COMMAND = re.compile(r"\\[a-zA-Z]+")


def numeric_signature(text: str) -> Tuple[str, ...]:
    """数字与 LaTeX 命令的有序序列:两题此签名不同 → 至多是变式题,不判为重复。"""
    return tuple(m.group(0) for m in re.finditer(f"{_NUMBER.pattern}|{_COMMAND.pattern}", text))


# --------------------------------------------------------------------------- #
# MinHash-LSH
# --------------------------------------------------------------------------- #
_MERSENNE = (1 << 61) - 1
_MAX_HASH = (1 << 32) - 1


def _perm_params() -> List[Tuple[int, int]]:
    params = []
    for i in range(NUM_PERM):
        digest = hashlib.blake2b(f"qb-dedup-{i}".encode(), digest_size=16).digest()
        a, b = struct.unpack("<QQ", digest)
        params.append(((a % (_MERSENNE - 1)) + 1, b % _MERSENNE))
    return params


_PERMS = _perm_params()


def shingles(text: str) -> set[str]:
    if len(text) <= SHINGLE_SIZE:
        return {text} if text else set()
    return {text[i:i + SHINGLE_SIZE] for i in range(len(text) - SHINGLE_SIZE + 1)}


def _h(s: str) -> int:
    return int.from_bytes(hashlib.blake2b(s.encode("utf-8"), digest_size=8).digest(), "little")


def minhash(text: str) -> List[int]:
    base = [_h(s) for s in shingles(text)]
    if not base:
        return [_MAX_HASH] * NUM_PERM
    return [min(((a * x + b) % _MERSENNE) & _MAX_HASH for x in base) for a, b in _PERMS]


def band_hashes(key: DedupKey) -> List[int]:
    """每个桶一个有符号 63 位整数(放得进 BIGINT)。题型参与哈希:不同题型不互相召回。"""
    if not key.fuzzy:
        return []
    sig = minhash(key.text)
    out = []
    for band in range(BANDS):
        chunk = sig[band * ROWS:(band + 1) * ROWS]
        raw = f"{key.q_type}|{band}|{','.join(map(str, chunk))}".encode()
        value = int.from_bytes(hashlib.blake2b(raw, digest_size=8).digest(), "little")
        out.append(value & ((1 << 63) - 1))
    return out


# --------------------------------------------------------------------------- #
# 相似度与差异
# --------------------------------------------------------------------------- #
def split_stimulus(text: str) -> Tuple[str, str]:
    """(材料, 题目本体)。没有材料时材料为空串。"""
    if _SEP_STIMULUS in text:
        stimulus, body = text.split(_SEP_STIMULUS, 1)
        return stimulus, body
    return "", text


def match_score(a: str, b: str) -> float:
    """两道题的相似度。带材料时材料与题目本体分别比、取较小值:
    同一材料下的不同小题,材料完全相同但本体不同,不能因材料占比大而被判相似。"""
    stim_a, body_a = split_stimulus(a)
    stim_b, body_b = split_stimulus(b)
    if stim_a or stim_b:
        return min(similarity(stim_a, stim_b), similarity(body_a, body_b))
    return similarity(a, b)


def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sa, sb = shingles(a), shingles(b)
    jaccard = len(sa & sb) / len(sa | sb) if sa and sb else 0.0
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    # quick_ratio 是 ratio 的上界:上界都不超过 jaccard 就不必算精确值
    if matcher.quick_ratio() <= jaccard:
        return jaccard
    return max(jaccard, matcher.ratio())


def diff_snippets(existing: str, incoming: str, limit: int = 3, context: int = 6) -> List[dict]:
    """归一化文本间的差异片段,供界面对比展示。"""
    matcher = difflib.SequenceMatcher(None, existing, incoming, autojunk=False)
    out = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        out.append({
            "before": existing[max(0, i1 - context):i1],
            "existing": existing[i1:i2],
            "incoming": incoming[j1:j2],
            "after": existing[i2:i2 + context],
        })
        if len(out) >= limit:
            break
    return out


def display_text(text: str) -> str:
    """归一化文本里的分隔符换成可读形式。"""
    return text.replace(_SEP_STIMULUS, " | ").replace(_SEP_OPTION, " / ")
