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
_BLOCKQUOTE_PREFIX_RE = re.compile(r'^\s*(?:>\s*)+')
_BLANK_UNDERSCORE_RE = re.compile(r'(?:\\?_){3,}')
# 【题目】标签之前的原卷题号(如 "3.【题目】" / "(3)【题目】");_TAG_RE 会吃掉它,故单独捕获。
_TAG_LEADING_NUMBER_RE = re.compile(r'^\s*(?:\*\*)?\(?(\d+(?:\.\d+)?)\)?[\.、．]?\s*[【\[]')
# 题干正文开头的题号(如 "【题目】3. 下列...");review 阶段会把它剔掉,故在此先行记录。
_CONTENT_LEADING_NUMBER_RE = re.compile(r'^\s*\(?(\d+(?:\.\d+)?)\)?[\.、．]\s*')
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
    return m.group(1) if m else None


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

    q_type = _map_q_type(q_type_raw) or _infer_q_type(options, answer, content)

    source_number: Optional[str] = None
    num_match = _CONTENT_LEADING_NUMBER_RE.match(content)
    if num_match:
        source_number = num_match.group(1)

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

    return {
        "content": content,
        "q_type": q_type,
        "options": options,
        "answer": answer,
        "thinking": thinking,
        "analysis": analysis,
        "summary": summary,
        "difficulty": difficulty,
        "warnings": warnings,
        "source_number": source_number,
    }


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

    for line in lines:
        tag = _match_tag(line)
        if tag and tag[0] == "content":
            flush_block()
            flush_text()
            block = [line]
            block_temp_id = str(uuid.uuid4())
            block_number = _leading_number_before_tag(line)
            continue

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
