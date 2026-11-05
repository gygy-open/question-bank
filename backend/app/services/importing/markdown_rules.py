"""零 AI 的 markdown 规则抽取：题干、选项、答案全部由可复算的脚本从原文切出。

为什么这条路要存在
------------------
把题干交给模型回写有问题，这是实测出来的，不是猜的。442K 字符 / 786 题的书：
- 模型只回 15 题（`finish=stop`，不是截断）；`max_tokens` 提到 131072 仍是 16 题；
- 强约束提示词要求"必须 786 题"，模型直接拒绝并回"原文过长，请分批"；
- 就算回得出来，它也会改写原文：`\\(...\\)`→`$...$`、
  `\\left( {{30}+{2m}}\\right)`→`(30+2m)`、`,若`→`，若`。

而"原文里写了答案"的题，脚本剥比模型判更可靠：同一本书实测脚本剥出 117 题、
模型只判出 85 题，两者一致的 14 题里，模型的判断没有提供额外信息。

所以抽取这一步可以完全不需要模型：
- 按行首题号切段（排除小数 3.14、排除解析里的 1）步骤编号）
- 剥选项块 → `options`（支持 A. / A、 / A) / A） / （A） 五种写法）
- 剥内联答案 `(B)` / `（ABD）` / `故选B` → `answer`
- 题型由结构推断（模型判题型实测不可靠：786 题里只判出 16 个选择题，
  而原文有 148 个带选项块的题）
- 难度由结构启发式给初值（可按学科提示词覆盖）
- 图片引用、公式原样保留，只做 `\\frac`→`\\dfrac` 这类排版升级

与"AI 做题"的分工
------------------
这条路只做抽取，**不判答案、不做题**。原文没写答案的题，`answer` 留空——
那些答案属于"做题"阶段，应该在题干被确认之后再生成（见 issue #22：
抽取 → 巡检 → 做题 → 回修）。把两步混在一起，题干有问题时做题结果会跟着错。

局限
----
- 不识别整卷/材料题结构（`paper` / `stimuli` / `question_groups`）。检测到这类文档
  直接报错，让人改用 `method="ai"`，而不是静默丢掉结构。
- 不做知识点富化（那需要模型）。知识点由后续富化或学科提示词负责。
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.importing.contracts import ExtractionResult

logger = logging.getLogger(__name__)

# 少于这个题数不值得走两阶段（小文件用原路径更稳）
# 行首题号：1. / 1． / 1、 / 1) / 1）
# 必须排除小数（3.14 不是第 3 题）：点号后不能紧跟数字。
# 必须排除解析里的 1） 这种：题号后要么是空白，要么紧接中文/字母（不能是"先化简"这类动词短语的判断交给
# 上层的 _split_stem_analysis 截断，这里只保证不把小数当成题号）。
NUM_RE = re.compile(r"^\s*(\d{1,3})\s*(?:[.．](?!\d)|、|[)）])\s*")

# 出现这些标签即认为题目正文已结束（避免把解析里的 1）2）当成新题）
SOLUTION_TAG_RE = re.compile(r"^\s*(?:解\s*[:：]|【\s*(?:解析|分析|详解|点睛|答案|考点|点评|小结|思路|解答)\s*】)")

# 选项块起点：A. / A、 / A) / A） / （A） / (A)
OPT_LABEL = r"[.．、)）]"
OPT_START_RE = re.compile(r"(?:^|\n)[ \t]*(?:[（(]\s*[A-D]\s*[)）]|[A-D]\s*" + OPT_LABEL + r")")
OPT_LETTER_RE = re.compile(r"(?:^|\s|\n)(?:[（(]\s*([A-D])\s*[)）]|([A-D])\s*" + OPT_LABEL + r")")

def _letters_in(text: str) -> List[str]:
    """从文本里抽出选项字母，兼容 A. / A、 / A) / A） / （A） 五种写法。"""
    out = []
    for m in OPT_LETTER_RE.finditer(text):
        lab = m.group(1) or m.group(2)
        if lab:
            out.append(lab.upper())
    return out


# 题干末尾内联答案：(B) / （B） / ( c ) / （ABD） 多选
INLINE_ANS_RE = re.compile(r"[\s，,、]?[（(]\s*([A-Da-d]{1,4})\s*[)）]\s*[。．.]?\s*$")
# 故选 B / 答案：B
TAIL_ANS_RE = re.compile(r"[\s，,、]?(?:故选|答案是|答案[：:])\s*([A-Da-d])\s*[。．.]?\s*$")
# 填空占位
BLANK_RE = re.compile(r"_{2,}|＿{2,}|（\s*）|\(\s*\)")

SYS_PROMPT = (
    "你是题目答案判定器。只输出 JSON，不要思考过程，不要 code fence，"
    "不要输出题干或解析。"
)

USER_PROMPT = """## 关键前提
原文是教辅书，每条题目前导是"数字."，共 {n} 条。注意原文题号每章从 1 重新开始，
所以题号会重复，**必须按出现顺序编号**，而不是按原文数字。

## 任务
按出现顺序（第1条、第2条……第 {n} 条）逐条**提取原文已经给出的答案**。

## 硬性要求
1. 输出必须正好 {n} 项，一项不漏，顺序与原文完全一致。
2. 不要回写题干，不要输出解析——题干由系统另取。
3. **只提取原文明确写出的答案，不要自己解题。** 原文没给答案就写空字符串 ""。
   不要推算、不要猜测、不要顺手做出来 —— 你产出的答案会被当成原文答案入库，
   自己算出来的答案一旦有错就会污染数据，比留空严重得多。
4. 答案来源：题干末尾或选项后有 `(B)` / `（B）` / `（ABD）` 就取该字母；填空看原文是否
   给出结果；解答看原文是否有"答案：/故/所以…=…"这类明确结论。
5. 禁止以"原文过长"为由拒绝或省略——你只输出答案，输出体积很小。

## 输出格式
{{"items":[{{"ord":1,"answer":"A"}},{{"ord":2,"answer":""}}]}}

## 原文
"""


# 整卷/材料题的信号：题组标签、材料标签、大分值、交卷标记
PAPER_SIGNAL_RE = re.compile(
    r"【\s*(?:题目材料|题组|题组结束)\s*】|"
    r"^\s*(?:第[一二三四五六七八九十]+[、.．]|[一二三四五六七八九十]+、)\s*$|"
    # 不能加 \b：中文词内全是 word 字符，"本卷满分" 里 卷/满 之间不存在边界，
    # 加了 \b 会漏掉前面带字的写法。
    r"(?:满分|共\s*\d+\s*分|考试时间)",
    re.M,
)


def _looks_like_paper(markdown: str) -> bool:
    """粗判是不是整卷/含材料题。命中就走原路径，保住 paper/stimuli/question_groups。"""
    return bool(PAPER_SIGNAL_RE.search(markdown))


# 括号型题号（1） / 1)）：在解析区里通常是步骤编号，不当成新题
PAREN_NUM_RE = re.compile(r"^\s*\d{1,3}\s*[)）]\s*")


def split_segments(markdown: str) -> List[List[str]]:
    """按行首题号把整篇原文切成若干题的原始行块（保留原行，便于后续逐字取用）。

    解析区内的 `1）` `2）` 是步骤编号，不是新题——进入解析后只有 `数字.` / `数字．` /
    `数字、` 才可能是新题。
    """
    lines = markdown.split("\n")
    starts: List[int] = []
    in_solution = False
    for i, line in enumerate(lines):
        if SOLUTION_TAG_RE.match(line):
            in_solution = True
            continue
        if not NUM_RE.match(line):
            continue
        if in_solution and PAREN_NUM_RE.match(line):
            continue          # 解析里的步骤编号
        starts.append(i)
        in_solution = False   # 出现真正的新题，退出解析区
    if not starts:
        return []
    segments: List[List[str]] = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        block = list(lines[start:end])
        block[0] = NUM_RE.sub("", block[0], count=1)
        segments.append(block)
    return segments


def _split_options(body: str) -> Tuple[str, str]:
    """把题块拆成 (题干, 选项块)。选项块必须含至少两个不同字母，否则不算。"""
    m = OPT_START_RE.search(body)
    if not m:
        return body, ""
    candidate = body[m.start():].lstrip("\n")
    # 选项块到解析标签为止：否则【解析】里的 "A. 错误 B. 正确" 会被当成新选项
    lines = candidate.split("\n")
    keep = []
    for ln in lines:
        if SOLUTION_TAG_RE.match(ln):
            break
        keep.append(ln)
    candidate = "\n".join(keep).strip()
    if len(set(_letters_in(candidate))) >= 2:
        return body[: m.start()].rstrip(), candidate
    return body, ""


def _options_to_list(options_block: str) -> List[str]:
    """把 'A. … B. … C. …' 拆成 ['A. …', 'B. …']，兼容 A) （A） 等写法。"""
    if not options_block:
        return []
    parts = re.split(r"(?:^|\s|\n)(?=(?:[（(]\s*[A-D]\s*[)）]|[A-D]\s*" + OPT_LABEL + r"))", options_block)
    out: List[str] = []
    seen = set()
    for p in parts:
        p = p.strip()
        if not (p and re.match(r"^(?:[（(]\s*[A-D]\s*[)）]|[A-D]\s*" + OPT_LABEL + r")", p)):
            continue
        lab = (_letters_in(p[:4]) or [""])[0]
        if not lab or lab in seen:
            continue
        # 同一段里若还嵌着下一个选项（"A. 甲 B. 乙"），在此截断
        inner = re.search(r"\s(?:[（(]\s*[A-D]\s*[)）]|[A-D]\s*" + OPT_LABEL + r")", p[1:])
        if inner:
            p = p[: inner.start() + 1].rstrip()
        out.append(p)
        seen.add(lab)
    letters = [(_letters_in(o[:4]) or [""])[0] for o in out]
    expect = [chr(65 + i) for i in range(len(letters))]
    return out if letters == expect else []


def _strip_inline_answer(stem: str) -> Tuple[str, str]:
    """从题干末尾剥出内联答案，返回 (干净题干, 答案字母)。"""
    for pat in (INLINE_ANS_RE, TAIL_ANS_RE):
        m = pat.search(stem)
        if m:
            return stem[: m.start()].rstrip(), m.group(1).upper()
    return stem, ""


def _sanitize_answer(q_type: str, answer: Any, options: List[str]) -> Any:
    """答案自检：解析不了就清空，绝不因为答案格式丢掉整道题。

    实测 786 题里有 7 道栽在这里，官方 `convert_answer` 会直接抛
    `LegacyQuestionError`，整题被 skip：
    - 选择题答案给了数字或结论文本（`3`、`y1<y3<y2`），抽不到选项字母
    - 填空答案含 `>`，被 markdown 当成引用块解析成空
    """
    if not answer:
        return answer

    if q_type in ("single_choice", "multiple_choice", "option_matching"):
        n = len(options)
        # 只接受落在选项范围内的字母
        letters = [c.upper() for c in re.findall(r"[A-Da-d]", str(answer))]
        letters = [c for c in letters if ord(c) - 65 < n]
        if not letters:
            # 退一步：用答案文本去匹配选项正文
            for i, opt in enumerate(options):
                text = re.sub(r"^\s*[A-Za-z]\s*[.．、)）]\s*", "", opt).strip()
                if len(text) >= 2 and text in str(answer):
                    letters.append(chr(65 + i))
        if not letters:
            return ""
        uniq = sorted(set(letters))
        return uniq[0] if q_type == "single_choice" else "".join(uniq)

    if q_type == "fill_in_the_blank":
        # 允许字符串或二维数组；元素做 markdown 安全转义，避免 `>` `<` `*` 被解析成结构
        def safe(v: Any) -> str:
            s = "" if v is None else str(v).strip()
            return re.sub(r"([<>*_`#~|])", r"\\\1", s) if s else ""

        if isinstance(answer, list):
            groups = []
            for g in answer:
                items = g if isinstance(g, list) else [g]
                cleaned = [safe(x) for x in items if safe(x)]
                groups.append(cleaned)
            return [g for g in groups if g] or ""
        return [[safe(answer)]] if safe(answer) else ""

    return answer


def _infer_q_type(stem: str, options: List[str], answer: str) -> str:
    """由结构推断题型。实测 AI 判题型不可靠，这里确定性判断。"""
    if options:
        letters = re.sub(r"[^A-Za-z]", "", answer or "")
        return "multiple_choice" if len(letters) > 1 else "single_choice"
    if BLANK_RE.search(stem):
        return "fill_in_the_blank"
    if re.search(r"_{2,}|＿{2,}", stem):
        return "fill_in_the_blank"
    return "free_response"


# 题干与「非题干内容」的分界：命中即认为题干到此结束
# 实测 442K 字符的教辅里，两题号之间混着 564 个 ## 标题、344 段 `解:` 解析、33 个【点睛】栏目
BOUNDARY_PATTERNS = (
    re.compile(r"^\s*解\s*[:：]"),                              # 解:(1)…
    re.compile(r"^\s*【\s*(?:解析|分析|详解|点睛|答案|考点|点评|小结|思路|解答)\s*】"),
    re.compile(r"^\s*(?:解析|分析|解答|点评|点睛|答案)\s*[:：]"),
    re.compile(r"^\s*#{1,6}\s*"),                               # 章节标题
    re.compile(r"^\s*\d{1,2}\s*[.．]\s*\d{1,2}\s+\S"),          # 25.2 降次——…（OCR 丢了 ### 的残句）
)

# 纯章节标题行（整行丢弃，不属于任何题目）
HEADING_LINE_RE = re.compile(r"^\s*#{1,6}\s*")
SECTION_TAIL_RE = re.compile(r"^\s*\d{1,2}\s*[.．]\s*\d{1,2}\s+\S.{0,40}$")


TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}")


def _split_trailing_table(text: str) -> Tuple[str, str]:
    """把题干末尾「不完整的表格残块」剥出去。

    实测 id=158 之类的题，末尾挂着 `|抛物线|开口方向|对称轴|` —— 那是上一节归纳
    表被 OCR 切断后粘到题干上的，既不属于这道题，也会让检索命中率变差。
    判据：从第一条 `|` 行到结尾，如果整块里没有 `| --- |` 分隔行，就是残块。
    """
    lines = text.split("\n")
    first = next((i for i, ln in enumerate(lines) if ln.strip().startswith("|")), None)
    if first is None:
        return text, ""
    block = lines[first:]
    if any(TABLE_SEP_RE.match(ln) for ln in block):
        return text, ""            # 是完整表格，属于题干，保留
    return "\n".join(lines[:first]).rstrip(), "\n".join(block).strip()


def _split_stem_analysis(body: str) -> Tuple[str, str]:
    """把题块拆成 (题干, 解析)。

    原文一道题后面常跟着完整解答（`解:` 起）与栏目（`【点睛】`），以前这些全被
    当成题干吞进去，实测最长一题被撑到 75,084 字符。
    """
    lines = body.split("\n")
    for i, line in enumerate(lines):
        if any(p.match(line) for p in BOUNDARY_PATTERNS):
            stem = "\n".join(lines[:i]).rstrip()
            analysis = "\n".join(lines[i:]).strip()
            return stem, analysis
    # 末尾残留的章节残句（如 "25.2 降次——解一元二次方"）也剥掉
    tail = len(lines) - 1
    while tail >= 0 and not lines[tail].strip():
        tail -= 1
    if tail > 0 and SECTION_TAIL_RE.match(lines[tail]):
        return "\n".join(lines[:tail]).rstrip(), lines[tail].strip()
    return body, ""


def _strip_headings(markdown: str) -> str:
    """删掉整行章节标题。标题是排版结构，不属于任何一道题的题干。"""
    kept = [ln for ln in markdown.split("\n") if not HEADING_LINE_RE.match(ln)]
    return "\n".join(kept)


def _upgrade_frac(text: str) -> str:
    r"""`\frac` → `\dfrac`，但上下标内的分式保留 `\frac`。

    用户要求：行内公式不缩小，分式按教材满尺寸排版；只有指数/下标里的分式才用
    `\frac`，否则 `\dfrac` 会撑坏行距。
    """
    if "\\frac" not in text:
        return text

    # 找出所有 ^{...} / _{...} 的字符区间，落在里面的 \frac 不动
    protected: List[Tuple[int, int]] = []
    for m in re.finditer(r"[\^_]\s*\{", text):
        depth = 0
        for i in range(m.end() - 1, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    protected.append((m.end() - 1, i))
                    break

    def in_script(pos: int) -> bool:
        return any(a <= pos <= b for a, b in protected)

    # \dfrac 不会命中：正则要求反斜杠后紧跟 frac
    hits = [(m.start(), m.end()) for m in re.finditer(r"\\frac(?![A-Za-z])", text)
            if not in_script(m.start())]
    if not hits:
        return text
    out = text
    for start, end in reversed(hits):
        out = out[:start] + "\\dfrac" + out[end:]
    return out


def _escape_blanks(stem: str) -> str:
    """转义连续下划线。

    Markdown 会把 `___4___` 解析成 bold+italic，下划线本身丢失（实测 786 题里 7 题
    因此失真）。填空横线是题目内容的一部分，必须用 `\\_` 转义保留为字面字符。
    """
    return re.sub(r"_{2,}", lambda m: "\\_" * len(m.group(0)), stem)


def _infer_difficulty(stem: str, options: List[str], q_type: str) -> int:
    """按文本特征估难度 1–5。

    官方 difficulty 只有 1–5 的档位，且接口不传会比全写成 1 更糟（筛选失效）。
    这里只用可从文本确定性算出的量，不调用 AI：
    - 字数、行内公式数、是否多小问、是否含证明/探究类动词。
    精确难度仍需人工或另跑模型，此值作为可用下限。
    """
    plain = re.sub(r"\s+", "", stem)
    n_chars = len(plain)
    n_math = stem.count("$") // 2
    score = 1
    if n_chars > 120:
        score += 1
    if n_chars > 260:
        score += 1
    if n_math > 4:
        score += 1
    if re.search(r"证明|求证|探究|综合|分类讨论|是否存在", stem):
        score += 1
    if re.search(r"[（(]\s*1\s*[)）][\s\S]*[（(]\s*2\s*[)）]", stem):
        score += 1
    return max(1, min(5, score))


def build_questions(segments: List[List[str]]) -> List[Dict[str, Any]]:
    """把切好的段组装成 legacy 形态的题目 dict（喂给 adapt_legacy_question）。

    答案只来自原文的内联标记。原文没写的就留空——那是"做题"阶段的事。
    """
    questions: List[Dict[str, Any]] = []
    for idx, block in enumerate(segments, start=1):
        body = _strip_headings("\n".join(block)).strip()
        if not body:
            continue
        stem, opt_block = _split_options(body)
        options = _options_to_list(opt_block)
        # 题干到此为止：后面是 解: / 【点睛】 / 章节标题，归入 analysis
        stem, table_tail = _split_trailing_table(stem)
        stem, analysis = _split_stem_analysis(stem)
        if table_tail:
            analysis = (analysis + "\n\n" + table_tail).strip() if analysis else table_tail
        stem, script_answer = _strip_inline_answer(stem)

        answer = script_answer
        q_type = _infer_q_type(stem, options, answer)
        difficulty = _infer_difficulty(stem, options, q_type)
        stem = _escape_blanks(_upgrade_frac(stem))

        # 填空题先按分隔符拆成多解，再统一自检：
        # 官方对填空题要求二维数组（外层=空，内层=可接受答案），给字符串会抛
        # LegacyQuestionError；而含 `>` 之类的答案会被 markdown 解析成空。
        if q_type == "fill_in_the_blank" and answer:
            answer = [
                a.strip() for a in re.split(r"[；;]|或|,|，|、", str(answer)) if a.strip()
            ]
        answer_value = _sanitize_answer(q_type, answer, options)

        questions.append(
            {
                "content": stem,
                "options": options,
                "answer": answer_value,
                "thinking": "",
                "analysis": _upgrade_frac(analysis),
                "summary": "",
                "difficulty": difficulty,
                "q_type": q_type,
            }
        )
    return questions


class RuleBasedExtractor:
    """零 AI 抽取：全部由可复算脚本完成，不依赖任何模型配置。"""

    async def extract(
        self,
        content: str,
        db: Optional[AsyncSession] = None,
        *,
        image_data: bytes | None = None,
        filename: str | None = None,
        mode: str = "extract",
        subject_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> ExtractionResult:
        # 规则抽取没有可切分的文本，图片要走视觉模型。
        if image_data:
            raise ValueError(
                "规则抽取不支持图片输入，请改用 method='ai' 走视觉模型"
            )

        # 整卷/材料题结构(paper/stimuli/question_groups)无法用规则还原；
        # 与其静默丢掉结构,不如让人显式改用 AI 路径。
        if _looks_like_paper(content):
            raise ValueError(
                "该文档含材料题/整卷结构，规则抽取无法保留题目材料与题组，"
                "请改用 method='ai'"
            )

        segments = split_segments(content)
        questions = build_questions(segments)
        for q in questions:
            q["id"] = str(uuid.uuid4())

        logger.info(
            "rule extract: %d segments -> %d questions (no AI)", len(segments), len(questions)
        )
        return ExtractionResult(
            questions=questions, stimuli=[], question_groups=[], paper=None
        )
