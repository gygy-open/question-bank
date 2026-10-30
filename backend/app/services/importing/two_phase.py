"""两阶段抽取：AI 只判答案，题干由原文确定性切分。

动机（实测依据）
----------------
1.6.0 的 `AIExtractor` 把整篇原文丢给模型，要求它回写完整题干。实测 442K 字符
/786 题的书，模型只出 15 题（`finish=stop`，不是截断）；把 `max_tokens` 提到
131072 仍是 16 题；用强约束提示词要求"必须 786 题"，模型直接拒绝并回
"原文过长，请分批"。

根因不是上下文，是**输出体积**：题干逐字照抄等于把整个文件再输出一遍。同一份
原文、同一次调用，只把输出改成 `{ord, answer, q_type}`（不回写题干），784→786 题
100% 穷举，78 秒完成。

而且题干由 AI 回写本来就有风险：实测它会改写 `\\(...\\)`→`$...$`、
`\\left( {{30}+{2m}}\\right)`→`(30+2m)`、`,若`→`，若`。改成从原文切片后，
题干在结构上不可能被改写。

设计
----
阶段 1（AI，整篇一次调用）：输出 `{"items":[{"ord":1,"answer":"A"}]}`，
`ord` 是**出现顺序**（1..N），不是原文题号——教辅书每章从 1 重新编号，题号会重复
786 次，不可用于对齐。

阶段 2（纯脚本）：
- 按行首题号切段
- 剥选项块 → `options`
- 剥内联答案 `(B)` / `( c )` / `故选B` → 脚本答案（比 AI 可靠）
- 脚本答案优先，缺失时用 AI 的
- `q_type` 由结构推断（AI 判题型实测不可靠：786 题里只判出 16 个选择题，
  而原文有 148 个带选项块的题）
- 图片引用原样保留

降级：题数少于 `MIN_Q`、或 AI 调用失败、或 AI 返回条目数与切段数不符时，
退回原始 `AIExtractor`，行为与未打补丁时一致。
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ai_provider import get_ai_provider
from app.services.importing.contracts import ExtractionResult
from app.services.importing.enrich import KnowledgePointEnricher

logger = logging.getLogger(__name__)

# 少于这个题数不值得走两阶段（小文件用原路径更稳）
MIN_Q = 20

# 行首题号：1. / 1． / 1、 / 1) / 1）
NUM_RE = re.compile(r"^\s*(\d{1,3})\s*[.．、)）]\s*")

# 选项块起点（行首或换行后的 A.）
OPT_START_RE = re.compile(r"(?:^|\n)[ \t]*[A-D]\s*[.．、]")
OPT_LETTER_RE = re.compile(r"(?:^|\s|\n)([A-D])\s*[.．、]")

# 题干末尾内联答案：(B) / （B） / ( c )
INLINE_ANS_RE = re.compile(r"[\s，,、]?[（(]\s*([A-Da-d])\s*[)）]\s*[。．.]?\s*$")
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
按出现顺序（第1条、第2条……第 {n} 条）逐条判断该题的答案。

## 硬性要求
1. 输出必须正好 {n} 项，一项不漏，顺序与原文完全一致。
2. 不要回写题干，不要输出解析——题干由系统另取，你只需判断答案。
3. 答案判定：该题末尾或选项后有 `(B)` / `（B）` / `( c )` 就取该字母；填空题为具体
   数值或表达式；解答题确实没有明确答案时写空字符串 ""。
4. 禁止以"原文过长"为由拒绝或省略——你只输出答案，输出体积很小。

## 输出格式
{{"items":[{{"ord":1,"answer":"A"}},{{"ord":2,"answer":""}}]}}

## 原文
"""


def split_segments(markdown: str) -> List[List[str]]:
    """按行首题号把整篇原文切成若干题的原始行块（保留原行，便于后续逐字取用）。"""
    lines = markdown.split("\n")
    starts = [i for i, line in enumerate(lines) if NUM_RE.match(line)]
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
    if len(set(OPT_LETTER_RE.findall(candidate))) >= 2:
        return body[: m.start()].rstrip(), candidate.strip()
    return body, ""


def _options_to_list(options_block: str) -> List[str]:
    """把 'A. … B. … C. …' 拆成 ['A. …', 'B. …']。"""
    if not options_block:
        return []
    parts = re.split(r"(?:^|\s|\n)(?=[A-D]\s*[.．、])", options_block)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if p and re.match(r"^[A-D]\s*[.．、]", p):
            out.append(p)
    return out


def _strip_inline_answer(stem: str) -> Tuple[str, str]:
    """从题干末尾剥出内联答案，返回 (干净题干, 答案字母)。"""
    for pat in (INLINE_ANS_RE, TAIL_ANS_RE):
        m = pat.search(stem)
        if m:
            return stem[: m.start()].rstrip(), m.group(1).upper()
    return stem, ""


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


def build_questions(
    segments: List[List[str]], ai_items: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """把切段 + AI 答案组装成 legacy 形态的题目 dict（喂给 adapt_legacy_question）。"""
    by_ord: Dict[int, str] = {}
    for item in ai_items:
        try:
            by_ord[int(item.get("ord"))] = (item.get("answer") or "").strip()
        except (TypeError, ValueError):
            continue

    questions: List[Dict[str, Any]] = []
    for idx, block in enumerate(segments, start=1):
        body = "\n".join(block).strip()
        if not body:
            continue
        stem, opt_block = _split_options(body)
        options = _options_to_list(opt_block)
        stem, script_answer = _strip_inline_answer(stem)

        ai_answer = by_ord.get(idx, "")
        # 脚本剥出的答案优先（确定性），AI 只补脚本剥不到的
        answer = script_answer or ai_answer
        q_type = _infer_q_type(stem, options, answer)

        questions.append(
            {
                "content": stem,
                "options": options,
                "answer": answer,
                "thinking": "",
                "analysis": "",
                "summary": "",
                "difficulty": 1,
                "q_type": q_type,
            }
        )
    return questions


class TwoPhaseExtractor:
    """整篇一次投：AI 判答案，脚本切题干。见模块 docstring 的实测依据。"""

    def __init__(self, enricher: Optional[KnowledgePointEnricher] = None) -> None:
        self.enricher = enricher or KnowledgePointEnricher()
        self._fallback = None  # 延迟构造，避免循环导入

    async def _ask_answers(
        self, content: str, config: Dict[str, Any], n: int
    ) -> List[Dict[str, Any]]:
        """整篇一次调用，只拿答案。失败抛异常，由调用方降级。"""
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=config.get("API_KEY"), base_url=config.get("BASE_URL")
        )
        messages = [
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": USER_PROMPT.format(n=n) + content},
        ]
        response = await client.chat.completions.create(
            model=config.get("MODEL_NAME", "gpt-4o"),
            messages=messages,
            response_format={"type": "json_object"},
            # 关键：不传 max_tokens 时上游默认额度会截断长输出；这里给足。
            max_tokens=131072,
        )
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise RuntimeError("answer phase output truncated (finish_reason=length)")
        raw = choice.message.content or ""
        payload = json.loads(raw)
        items = payload.get("items") or payload.get("answers") or []
        if isinstance(items, list) and items and isinstance(items[0], str):
            items = [{"ord": i + 1, "answer": a} for i, a in enumerate(items)]
        return items

    async def extract(
        self,
        content: str,
        db: AsyncSession,
        *,
        image_data: bytes | None = None,
        filename: str | None = None,
        mode: str = "extract",
        subject_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> ExtractionResult:
        # 图片整页 OCR 路径不走两阶段（没有可切分的 markdown）
        if image_data:
            return await self._fallback_extract(
                content, db, image_data=image_data, filename=filename,
                mode=mode, subject_id=subject_id, user_id=user_id,
            )

        segments = split_segments(content)
        if len(segments) < MIN_Q:
            logger.info(
                "two-phase skipped: %d segments < MIN_Q(%d), falling back",
                len(segments), MIN_Q,
            )
            return await self._fallback_extract(
                content, db, filename=filename, mode=mode,
                subject_id=subject_id, user_id=user_id,
            )

        from app.services.importing.provider_config import resolve_active_provider

        provider_name, config = await resolve_active_provider(
            db, is_vision=False, user_id=user_id
        )
        if provider_name is None:
            logger.warning("two-phase: no active AI provider, falling back")
            return await self._fallback_extract(
                content, db, filename=filename, mode=mode,
                subject_id=subject_id, user_id=user_id,
            )

        try:
            ai_items = await self._ask_answers(content, config, len(segments))
        except Exception as exc:  # noqa: BLE001 - 降级优于失败
            logger.warning("two-phase answer phase failed, falling back: %s", exc)
            return await self._fallback_extract(
                content, db, filename=filename, mode=mode,
                subject_id=subject_id, user_id=user_id,
            )

        covered = len({i.get("ord") for i in ai_items})
        logger.info(
            "two-phase: %d segments, AI answered %d (%.0f%%)",
            len(segments), covered, covered / len(segments) * 100,
        )

        questions = build_questions(segments, ai_items)
        if not questions:
            return ExtractionResult()

        # 知识点富化沿用官方实现（向量召回 + AI rerank）
        provider = get_ai_provider(provider_name)
        try:
            await self.enricher.enrich(
                [_EnrichShim(q) for q in questions],
                subject_id=subject_id, provider=provider, config=config,
            )
        except Exception as exc:  # noqa: BLE001 - 富化失败不影响入库
            logger.warning("two-phase: knowledge point enrich failed: %s", exc)

        for q in questions:
            q["id"] = str(uuid.uuid4())

        return ExtractionResult(questions=questions, stimuli=[], question_groups=[], paper=None)

    async def _fallback_extract(self, content: str, db: AsyncSession, **kwargs: Any) -> ExtractionResult:
        if self._fallback is None:
            from app.services.importing.extract import AIExtractor
            self._fallback = AIExtractor()
        return await self._fallback.extract(content, db, **kwargs)


class _EnrichShim:
    """官方 KnowledgePointEnricher 读 .content / .knowledge_points 属性，
    这里把 dict 包一层，避免为了富化把题目转成 AIQuestion。"""

    __slots__ = ("_d", "content", "knowledge_points", "knowledge_point_ids")

    def __init__(self, d: Dict[str, Any]) -> None:
        self._d = d
        self.content = d.get("content", "")
        self.knowledge_points: List[str] = []
        self.knowledge_point_ids: List[int] = []

    def __getattr__(self, name: str) -> Any:
        try:
            return self._d[name]
        except KeyError:
            raise AttributeError(name) from None
