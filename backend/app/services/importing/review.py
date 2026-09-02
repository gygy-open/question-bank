"""抽取产物(legacy raw dict) → 可复核的 v2 草稿(不落库)。

供 /upload/* 同步复核路径:把抽取器输出的旧 Markdown 题目清洗(去题号、推断类型、
归并 AI 建议标签)并经 `adapt_legacy_question` 统一转 v2,前端拿到即用新编辑器编辑,
无需再单独调用转换接口。转换规则仍走单一漏斗,不重写。

与 worker/batch-legacy 的落库路径(`QuestionImporter.import_batch`)区分:那条路径
消费的是前端已复核的数据,此处只负责"抽取 → 可编辑草稿"这一同步阶段。
"""
from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional, Sequence

from app.models.question import QuestionStatus
from app.services.question_legacy_adapter import (
    LegacyQuestionError,
    adapt_legacy_question,
)

from .normalize import coerce_kp_ids, coerce_q_type

logger = logging.getLogger(__name__)

# 行首题号:如 "1. " / "1、" / "(1) "。抽取产物常带原文序号,编辑前去掉。
_LEADING_NUMBER_RE = re.compile(r"^(?:\d+[.、\s]\s*|\(\d+\)\s*)")

# AI/结构化解析可能在顶层给出的标签类目,归并到 ai_suggested_tags 供人工确认。
_AI_TAG_CATEGORIES = ("year", "source", "grade", "semester", "exam_type", "feature")


def _clean_content(raw: Any) -> str:
    if raw is None:
        return ""
    return _LEADING_NUMBER_RE.sub("", str(raw))


def _build_ai_tags(raw: Mapping[str, Any]) -> Optional[dict[str, list[str]]]:
    tags: dict[str, list[str]] = {}
    for cat in _AI_TAG_CATEGORIES:
        val = raw.get(cat)
        if isinstance(val, list):
            tags[cat] = [str(v) for v in val]
        elif isinstance(val, str) and val:
            tags[cat] = [val]
    generic = raw.get("tags")
    if isinstance(generic, list) and generic:
        merged = list(dict.fromkeys([*tags.get("ai_extracted", []), *(str(t) for t in generic)]))
        tags["ai_extracted"] = merged
    return tags or None


def extracted_to_v2_review(
    raws: Sequence[Mapping[str, Any]],
    *,
    subject_id: Optional[int] = None,
    default_status: QuestionStatus = QuestionStatus.PENDING,
) -> list[dict[str, Any]]:
    """把抽取器原始输出转成 v2 草稿 dict 列表(不落库)。

    - 答案无法解析:保留题干/选项,答案降级为 None 并附 warning,交前端结构化补齐。
    - 硬错误(如题干为空):跳过并记日志,不返回不可编辑的空题。
    """
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(raws):
        q_type = coerce_q_type(raw.get("q_type", raw.get("type")))
        content = _clean_content(raw.get("content"))
        warnings: list[str] = list(raw.get("warnings") or []) if isinstance(raw.get("warnings"), list) else []

        try:
            v2 = adapt_legacy_question(
                q_type=q_type,
                status=default_status,
                content=content,
                options=raw.get("options"),
                answer=raw.get("answer"),
                thinking=raw.get("thinking"),
                analysis=raw.get("analysis"),
                summary=raw.get("summary"),
            )
        except LegacyQuestionError as exc:
            try:
                v2 = adapt_legacy_question(
                    q_type=q_type,
                    status=default_status,
                    content=content,
                    options=raw.get("options"),
                    answer=None,
                    thinking=raw.get("thinking"),
                    analysis=raw.get("analysis"),
                    summary=raw.get("summary"),
                )
            except LegacyQuestionError as exc2:
                logger.warning("review: skip un-adaptable question #%d: %s", index, exc2)
                continue
            warnings += list(exc.warnings) or [str(exc)]

        out.append(
            {
                "q_type": q_type.value,
                "content": v2["content"],
                "options": v2["options"],
                "answer": v2["answer"],
                "thinking": v2["thinking"],
                "analysis": v2["analysis"],
                "summary": v2["summary"],
                "difficulty": raw.get("difficulty", 1) or 1,
                "status": v2["status"],
                "knowledge_point_ids": coerce_kp_ids(raw.get("knowledge_point_ids")),
                "subject_id": raw.get("subject_id") or subject_id,
                "ai_suggested_tags": _build_ai_tags(raw),
                "warnings": warnings,
            }
        )
    return out
