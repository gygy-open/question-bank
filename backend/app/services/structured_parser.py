"""
Structured (tag-based) question parser.

A deterministic, AI-free parser that turns documents authored with explicit
tags (e.g. 【题目】【选项】【答案】【解析】) into structured question dicts.

Design: "【题目】切块 + 字段状态机 + 白名单行首标签 + 尽力解析并收集告警".
The output shape matches what the AI extraction path returns so it can flow
through the same frontend review -> import pipeline.

除题目外还产出整卷结构(outline):大题标题与题间说明文字不再丢弃,而是按版面
顺序记录,供“导入同时保存为稿件”还原原卷。
"""
import json
import re
import uuid
from collections import defaultdict
from typing import List, Dict, Optional, Tuple

from app.services.importing.contracts import (
    OUTLINE_HEADING,
    OUTLINE_QUESTION_REF,
    OUTLINE_RICH_TEXT,
    ExtractionResult,
    PaperOutlineItem,
)

# --- Tag whitelist: alias -> canonical field ---
TAG_ALIASES = {
    # content (also the record boundary)
    "题目": "content", "题干": "content", "question": "content", "title": "content",
    # question type
    "题型": "q_type", "类型": "q_type", "type": "q_type",
    # options (block form)
    "选项": "options", "options": "options",
    # answer
    "答案": "answer", "参考答案": "answer", "answer": "answer",
    # analysis
    "解析": "analysis", "详解": "analysis", "解答": "analysis", "analysis": "analysis",
    # thinking
    "思路": "thinking", "分析": "thinking", "thinking": "thinking",
    # summary
    "小结": "summary", "总结": "summary", "summary": "summary",
    # difficulty
    "难度": "difficulty", "difficulty": "difficulty",
    # knowledge point (consumed but not emitted in MVP)
    "知识点": "knowledge_point", "knowledge_point": "knowledge_point",
}

# 文档级分区标签(与上面的逐题字段标签分属不同命名空间,只在题块之外生效):
# 标记之后的内容是「统一答案区」——答案表(表格)给答案、编号段落给解析,
# 按题号回填到已解析的题目,而不是当作某一题的字段。
SECTION_TAG_ALIASES = {
    "答案区": "answer_section", "答案表": "answer_section",
    "统一答案": "answer_section", "答案速查": "answer_section",
}

_Q_TYPE_MAP = {
    "单选": "single_choice", "单选题": "single_choice", "single_choice": "single_choice",
    "多选": "multiple_choice", "多选题": "multiple_choice", "multiple_choice": "multiple_choice",
    "判断": "true_false", "判断题": "true_false", "true_false": "true_false",
    "填空": "fill_in_the_blank", "填空题": "fill_in_the_blank",
    "fill_in_the_blank": "fill_in_the_blank",
    "解答": "free_response", "解答题": "free_response",
    "简答": "free_response", "简答题": "free_response",
    "主观": "free_response", "主观题": "free_response", "free_response": "free_response",
}

_CN_DIFFICULTY = {"简单": 1, "容易": 1, "较易": 2, "中等": 3, "普通": 3, "较难": 4, "困难": 5, "难": 5}

_TRUE_FALSE_ANSWERS = {
    "对", "错", "正确", "错误", "√", "×", "T", "F", "t", "f",
    "true", "false", "是", "否", "yes", "no", "Y", "N",
}

# Optional leading numbering like "1." "1、" "(1)" before a tag, then a bracketed
# tag using full-width 【】 or half-width [], then optional colon, then inline text.
_TAG_RE = re.compile(
    r'^\s*(?:\*\*)?(?:\(?\d+\)?[\.、\．]?\s*)?[【\[]\s*([^\]】]+?)\s*[】\]]'
    r'(?:\*\*)?\s*[:：]?\s*(.*?)\s*(?:\*\*)?\s*$'
)

_OPTION_TAG_RE = re.compile(r'^(?:选项|option)\s*([A-Za-z])$', re.IGNORECASE)
_BRACKET_TAG_RE = re.compile(r'[【\[]\s*([^\]】]+?)\s*[】\]]')
_BLOCKQUOTE_PREFIX_RE = re.compile(r'^\s*(?:>\s*)+')
_BLANK_UNDERSCORE_RE = re.compile(r'(?:\\?_){3,}')
# 【题目】标签之前的原卷题号(如 "3.【题目】" / "(3)【题目】");_TAG_RE 会吃掉它,故单独捕获。
_TAG_LEADING_NUMBER_RE = re.compile(r'^\s*(?:\*\*)?\(?(\d+(?:\.\d+)?)\)?[\.、．]?\s*[【\[]')
# 题干正文开头的题号(如 "【题目】3. 下列...");review 阶段会把它剔掉,故在此先行记录。
_CONTENT_LEADING_NUMBER_RE = re.compile(r'^\s*\(?(\d+(?:\.\d+)?)\)?[\.、．]\s*')
# 统一答案区里,编号段落的题号(如 "1．B因为..."),用作该题解析的记录边界。
_ANALYSIS_ITEM_RE = re.compile(r'^\s*(\d+)[\.、．]\s*')
_HEADING_MARKUP_RE = re.compile(r'^[\s#*>]+|[\s*]+$')
_INLINE_ANALYSIS_TAG_RE = re.compile(
    r'(?=[【\[]\s*(?:解析|详解|解答|analysis)\s*[】\]])',
    re.IGNORECASE,
)
_SECTION_HEADING_RE = re.compile(
    r'^\s*(?:\*\*)?(?:#{1,6}\s*)?'
    r'(?:[一二三四五六七八九十百]+|\d+)\s*[、\.．]\s*'
    r'(?:单选|多选|选择|填空|判断|解答|简答|综合).*题',
)


def _strip_blockquote_prefix(line: str) -> str:
    return _BLOCKQUOTE_PREFIX_RE.sub('', line, count=1)


def _is_section_heading(line: str) -> bool:
    return bool(_SECTION_HEADING_RE.match(line))


def _heading_text(line: str) -> str:
    """去掉 Markdown 标题标记与加粗星号,取可读的大题标题文本。"""
    return _HEADING_MARKUP_RE.sub('', line).strip()


def _leading_number_before_tag(line: str) -> Optional[str]:
    m = _TAG_LEADING_NUMBER_RE.match(line)
    return _normalize_number(m.group(1)) if m else None


def _normalize_number(raw: Optional[str]) -> Optional[str]:
    """去掉纯数字题号的前导零,形如 3.1 的子题号原样保留。"""
    if not raw:
        return None
    raw = raw.strip()
    return str(int(raw)) if raw.isdigit() else raw


def _match_section_tag(line: str) -> Optional[Tuple[str, str]]:
    """识别文档级分区标签(如【答案区】)。标签常跟在"参考答案"等标题文字之后,
    不要求出现在行首,故用 search 而非 match;返回 (kind, 标签前的标题文字)。"""
    for m in _BRACKET_TAG_RE.finditer(line):
        raw_name = m.group(1).strip()
        kind = SECTION_TAG_ALIASES.get(raw_name) or SECTION_TAG_ALIASES.get(raw_name.lower())
        if kind:
            return kind, _heading_text(line[:m.start()])
    return None


def _match_tag(line: str) -> Optional[Tuple[str, str, Optional[str]]]:
    """
    Return (field, inline_content, option_letter) if the line starts with a
    known whitelist tag, else None. option_letter is set only for per-option
    tags like 【选项A】.
    """
    m = _TAG_RE.match(line)
    if not m:
        return None
    raw_name = m.group(1).strip()
    inline = m.group(2)

    om = _OPTION_TAG_RE.match(raw_name)
    if om:
        return ("option_item", inline, om.group(1).upper())

    field = TAG_ALIASES.get(raw_name) or TAG_ALIASES.get(raw_name.lower())
    if field is None:
        # Unknown bracketed text -> not a delimiter, treat as content.
        return None
    return (field, inline, None)


def _split_option_block(text: str) -> List[str]:
    """Split a single 【选项】 block into ["A. ...", "B. ...", ...]."""
    pattern = re.compile(r'(?<!\S)([A-Za-z])\s*[\.、\)．]\s*')
    matches = list(pattern.finditer(text))
    if not matches:
        return []
    options: List[str] = []
    for i, mt in enumerate(matches):
        start = mt.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        label = mt.group(1).upper()
        content = text[start:end].strip()
        options.append(f"{label}. {content}")
    return options


def _map_q_type(raw: str) -> Optional[str]:
    if not raw:
        return None
    key = raw.splitlines()[0].strip()
    return _Q_TYPE_MAP.get(key) or _Q_TYPE_MAP.get(key.lower())


def _infer_q_type(options: List[str], answer: str, content: str) -> str:
    a = (answer or "").strip()
    if options:
        letters = re.findall(r'[A-Za-z]', a)
        if len(letters) >= 2:
            return "multiple_choice"
        return "single_choice"
    if a in _TRUE_FALSE_ANSWERS:
        return "true_false"
    if _BLANK_UNDERSCORE_RE.search(content) or "（）" in content or "（  ）" in content:
        return "fill_in_the_blank"
    return "free_response"


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith('|') and stripped.count('|') >= 2


def _split_table_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip('|').split('|')]


def _is_table_separator_row(cells: List[str]) -> bool:
    return all(re.fullmatch(r':?-+:?', c) for c in cells if c)


def _strip_cell_markup(cell: str) -> str:
    return cell.strip('* ').strip()


def _extract_answer_table(rows: List[List[str]]) -> Dict[str, str]:
    """从形如 “题号|1|2|3” + “答案|B|B|C” 的两行表格中取 题号->答案。"""
    header_row: Optional[List[str]] = None
    for row in rows:
        if _is_table_separator_row(row):
            continue
        if header_row is None:
            if any("题号" in cell for cell in row):
                header_row = row
            continue
        answers: Dict[str, str] = {}
        for num_cell, ans_cell in zip(header_row, row):
            num = _strip_cell_markup(num_cell)
            ans = _strip_cell_markup(ans_cell)
            if num.isdigit() and ans:
                answers[num] = ans
        return answers
    return {}


def _strip_leading_answer(text: str, answer: str) -> str:
    """解析段落常在题号后原样抄写答案(如 "10．ACD对于..."),这段与答案表重复,故去掉前缀。"""
    if not answer:
        return text
    stripped = text.lstrip()
    if stripped[:len(answer)].upper() == answer.upper():
        return stripped[len(answer):].lstrip()
    return text


def _split_tagged_record(parts: List[str]) -> Tuple[Optional[str], Optional[str], str]:
    """答案区里某道题若显式写了【答案】/【解析】标签,其可靠性等同逐题解析,应优先采用；
    返回 (显式答案, 显式解析, 原始拼接文本)，未打标签时前两者为 None。"""
    raw_text = "\n".join(parts).strip()
    fields: Dict[str, List[str]] = defaultdict(list)
    current_field: Optional[str] = None
    found_tag = False

    for line in parts:
        t = _match_tag(line)
        if t and t[0] in ("answer", "analysis"):
            found_tag = True
            current_field = t[0]
            if t[1].strip():
                fields[current_field].append(t[1])
        elif t:
            current_field = None
        elif current_field is not None and line.strip():
            fields[current_field].append(line)

    if not found_tag:
        return None, None, raw_text
    return (
        "\n".join(fields.get("answer", [])).strip() or None,
        "\n".join(fields.get("analysis", [])).strip() or None,
        raw_text,
    )


def _split_answer_section_outline(lines: List[str]) -> List[PaperOutlineItem]:
    """按表格行/非表格行分组分别出块,而不是拼成一整段 markdown——否则表格解析器会把
    表格后面紧跟着的解析段落也当成表格的后续行吞进去(行间空行在预处理阶段已被过滤)。"""
    items: List[PaperOutlineItem] = []
    current: List[str] = []
    current_is_table: Optional[bool] = None

    for line in lines:
        is_table = _is_table_row(line)
        if current and is_table != current_is_table:
            markdown = "\n".join(current).strip()
            if markdown:
                items.append({"kind": OUTLINE_RICH_TEXT, "markdown": markdown})
            current = []
        current.append(line)
        current_is_table = is_table

    markdown = "\n".join(current).strip()
    if markdown:
        items.append({"kind": OUTLINE_RICH_TEXT, "markdown": markdown})
    return items


def _parse_answer_section(lines: List[str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """解析【答案区】之后的内容:每道题若显式写了【答案】/【解析】标签则直接采用;
    否则退回表格给 answer、编号段落整体作 analysis(并去掉开头重复抄写的答案)。"""
    table_rows: List[List[str]] = []
    records: Dict[str, List[str]] = defaultdict(list)
    current_number: Optional[str] = None

    for line in lines:
        if _is_table_row(line):
            table_rows.append(_split_table_row(line))
            current_number = None
            continue
        m = _ANALYSIS_ITEM_RE.match(line)
        if m:
            current_number = _normalize_number(m.group(1))
            rest = line[m.end():]
            if current_number and rest.strip():
                records[current_number].append(rest)
            continue
        if current_number and line.strip():
            records[current_number].append(line)

    answers: Dict[str, str] = dict(_extract_answer_table(table_rows))
    analyses: Dict[str, str] = {}
    for num, parts in records.items():
        tagged_answer, tagged_analysis, raw_text = _split_tagged_record(parts)
        if tagged_answer:
            answers[num] = tagged_answer
        analyses[num] = (
            tagged_analysis if tagged_analysis is not None
            else _strip_leading_answer(raw_text, answers.get(num, ""))
        )

    return answers, analyses


def _build_question(fields: Dict[str, List[str]],
                    option_items: Dict[str, List[str]]) -> dict:
    def join(field: str) -> str:
        return "\n".join(fields.get(field, [])).strip()

    content = join("content")
    answer = join("answer")
    analysis = join("analysis")
    thinking = join("thinking")
    summary = join("summary")
    difficulty_raw = join("difficulty")
    q_type_raw = join("q_type")

    # Options: per-option tags take precedence over a single 【选项】 block.
    options: List[str] = []
    if option_items:
        for letter in sorted(option_items.keys()):
            opt_text = "\n".join(option_items[letter]).strip()
            options.append(f"{letter}. {opt_text}")
    elif fields.get("options"):
        options = _split_option_block("\n".join(fields["options"]))

    # Difficulty (1-5).
    difficulty = 1
    if difficulty_raw:
        dm = re.search(r'\d+', difficulty_raw)
        if dm:
            difficulty = max(1, min(5, int(dm.group())))
        else:
            difficulty = _CN_DIFFICULTY.get(difficulty_raw.strip(), 1)

    source_number: Optional[str] = None
    num_match = _CONTENT_LEADING_NUMBER_RE.match(content)
    if num_match:
        source_number = _normalize_number(num_match.group(1))

    question = {
        "content": content,
        "q_type": None,
        "options": options,
        "answer": answer,
        "thinking": thinking,
        "analysis": analysis,
        "summary": summary,
        "difficulty": difficulty,
        "warnings": [],
        "source_number": source_number,
        # 文末答案区回填 answer 后需要重新推断 q_type，故显式标签的结果先记下，
        # 不在这里直接 pop——parse_structured 收尾时才统一清理。
        "_q_type_explicit": _map_q_type(q_type_raw),
    }
    _finalize_question(question)
    return question


def _finalize_question(question: dict) -> None:
    """推导 q_type、规整填空题答案、生成 warnings；答案区回填后会被再次调用。"""
    content = question["content"]
    options = question["options"]
    answer = question["answer"]
    q_type = question.get("_q_type_explicit") or _infer_q_type(options, answer, content)

    if q_type == "fill_in_the_blank" and answer:
        try:
            parsed_answer = json.loads(answer)
        except json.JSONDecodeError:
            parsed_answer = None
        if not isinstance(parsed_answer, list):
            answer = json.dumps([[answer]], ensure_ascii=False)

    warnings: List[str] = []
    if not content:
        warnings.append("题干为空")
    if q_type in ("single_choice", "multiple_choice"):
        if not options:
            warnings.append("选择题缺少选项")
        if not answer:
            warnings.append("选择题缺少答案")
        elif options:
            labels = {o[0].upper() for o in options if o}
            for ch in re.findall(r'[A-Za-z]', answer):
                if ch.upper() not in labels:
                    warnings.append(f"答案 {ch.upper()} 超出选项范围")
                    break

    question["q_type"] = q_type
    question["answer"] = answer
    question["warnings"] = warnings


def _parse_block(lines: List[str]) -> dict:
    fields: Dict[str, List[str]] = defaultdict(list)
    option_items: Dict[str, List[str]] = {}
    current_field: Optional[str] = None
    current_option: Optional[str] = None

    for line in lines:
        t = _match_tag(line)
        if t:
            field, inline, opt_letter = t
            if field == "option_item":
                current_field = "option_item"
                current_option = opt_letter
                option_items.setdefault(opt_letter, [])
                if inline.strip():
                    option_items[opt_letter].append(inline)
            else:
                current_field = field
                current_option = None
                if inline.strip():
                    fields[field].append(inline)
        elif _is_section_heading(line):
            current_field = None
            current_option = None
        else:
            if current_field == "option_item" and current_option is not None:
                option_items[current_option].append(line)
            elif current_field is not None:
                fields[current_field].append(line)
            # Lines before any tag inside a block are ignored (block starts at 【题目】).

    return _build_question(fields, option_items)


def parse_structured(text: str) -> ExtractionResult:
    """
    Parse tag-annotated text into questions plus the paper outline.

    Uses 【题目】 (content) as the record boundary. Missing tags simply leave
    the corresponding field empty; per-question issues are collected into a
    "warnings" list instead of raising.

    大题标题与题间说明不再被丢弃：它们按版面顺序进入 outline，题目则以
    question_ref 占位，两者通过 temp_id 关联。
    """
    lines = [
        part
        for line in (text or "").splitlines()
        for part in _INLINE_ANALYSIS_TAG_RE.split(_strip_blockquote_prefix(line))
        if part
    ]

    questions: List[dict] = []
    outline: List[PaperOutlineItem] = []
    block: Optional[List[str]] = None
    block_temp_id: Optional[str] = None
    block_number: Optional[str] = None
    pending_text: List[str] = []

    def flush_text() -> None:
        markdown = "\n".join(pending_text).strip()
        pending_text.clear()
        if markdown:
            outline.append({"kind": OUTLINE_RICH_TEXT, "markdown": markdown})

    def flush_block() -> None:
        nonlocal block, block_temp_id, block_number
        if block is None:
            return
        question = _parse_block(block)
        question["id"] = block_temp_id
        # 标签前的原卷题号优先于题干正文里的题号。
        number = block_number or question.get("source_number")
        question["source_number"] = number
        questions.append(question)
        outline.append(
            {"kind": OUTLINE_QUESTION_REF, "temp_id": block_temp_id, "number": number}
        )
        block = None
        block_temp_id = None
        block_number = None

    answer_section_lines: Optional[List[str]] = None

    for i, line in enumerate(lines):
        tag = _match_tag(line)
        if tag and tag[0] == "content":
            flush_block()
            flush_text()
            block = [line]
            block_temp_id = str(uuid.uuid4())
            block_number = _leading_number_before_tag(line)
            continue

        # 【答案区】标志全卷答案/解析统一收尾：无论当前题块是否还开着都直接结束扫描，
        # 其后内容整体移交单独解析，不再走逐题字段状态机。
        section = _match_section_tag(line)
        if section and section[0] == "answer_section":
            flush_block()
            flush_text()
            prefix_heading = section[1]
            if prefix_heading:
                outline.append({"kind": OUTLINE_HEADING, "text": prefix_heading, "level": 2})
            answer_section_lines = lines[i + 1:]
            break

        # 大题标题是版面结构而非题目字段，遇到即结束当前题块。
        if _is_section_heading(line):
            flush_block()
            flush_text()
            heading = _heading_text(line)
            if heading:
                outline.append({"kind": OUTLINE_HEADING, "text": heading, "level": 2})
            continue

        if block is not None:
            block.append(line)
        elif line.strip():
            pending_text.append(line)

    flush_block()
    flush_text()

    if answer_section_lines is not None:
        answers_by_number, analyses_by_number = _parse_answer_section(answer_section_lines)
        for question in questions:
            number = question.get("source_number")
            if not number:
                continue
            if not question["answer"] and number in answers_by_number:
                question["answer"] = answers_by_number[number]
            if not question["analysis"] and number in analyses_by_number:
                question["analysis"] = analyses_by_number[number]
            _finalize_question(question)
        outline.extend(_split_answer_section_outline(answer_section_lines))

    for question in questions:
        question.pop("_q_type_explicit", None)

    suggested_title = _take_suggested_title(outline)
    return ExtractionResult(
        questions=questions,
        paper={"suggested_title": suggested_title, "outline": outline},
    )


def _take_suggested_title(outline: List[PaperOutlineItem]) -> Optional[str]:
    """把首个结构项之前的第一行文字视为试卷标题，并从 outline 中消费掉它。"""
    if not outline or outline[0].get("kind") != OUTLINE_RICH_TEXT:
        return None
    first = outline[0]
    parts = (first.get("markdown") or "").split("\n", 1)
    title = _heading_text(parts[0])
    if not title:
        return None
    rest = parts[1].strip() if len(parts) > 1 else ""
    if rest:
        first["markdown"] = rest
    else:
        outline.pop(0)
    return title
