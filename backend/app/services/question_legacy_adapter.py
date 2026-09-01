"""旧题目 payload → 严格 v2 QuestionCreate 字段的统一 adapter(仅用于 legacy 路径)。

用于把「旧字符串形态」的题目(AI 抽取 / 结构化解析 / 聊天工具提议)转换成 v2 富文本对象:
- content/thinking/analysis/summary:Markdown → RichDoc。
- options:List[str]("A. 内容" 或纯内容)或 List[{label, content}] → [{id, label, content: RichDoc}]。
- answer:旧字符串/列表 → AnswerSpec 判别联合。

关键约束(见 docs/development/question-model-v2.md §7/§10):
- 普通新导入**不得**静默写入 `legacy_unresolved`:选择/判断/填空答案无法解析时抛
  `LegacyQuestionError`,由调用方按既有任务机制标失败/告警。
- 答案**完全缺失**(而非无法解析)时不拒绝导入:返回的 `status` 会从 pending/published
  降级为 draft,完整性校验交给消费端(发布/组卷/导出,见 §11)。
- 只用于 legacy 路径;已是 v2 的对象不要再经过本 adapter(避免重复转换)。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from app.services.question_content_converter import (
    convert_answer,
    make_option_id,
    markdown_to_rich_doc,
)

__all__ = ["LegacyQuestionError", "adapt_legacy_question"]

_CHOICE_TYPES = {"single_choice", "multiple_choice"}
# 旧选项字符串的行首 label,如 "A. xxx" / "A、xxx" / "A) xxx" / "A：xxx"。
_OPTION_LABEL_RE = re.compile(r"^\s*([A-Za-z])\s*[\.、\)．:：]\s*(.*)$", re.DOTALL)


class LegacyQuestionError(ValueError):
    """legacy payload 无法安全转成严格 v2(不允许静默持久化 legacy_unresolved)。"""

    def __init__(self, message: str, *, warnings: Optional[list[str]] = None) -> None:
        super().__init__(message)
        self.warnings = warnings or []


def _q_type_value(q_type: Any) -> str:
    return getattr(q_type, "value", q_type)


def _normalize_legacy_options(raw_options: Any) -> list[dict[str, Any]]:
    """把旧 options 归一为 [{id, label, content: RichDoc}],label 缺失时按序补 A/B/C…。"""
    if not isinstance(raw_options, list):
        return []
    out: list[dict[str, Any]] = []
    for index, opt in enumerate(raw_options):
        label = ""
        content_md = ""
        if isinstance(opt, dict):
            label = str(opt.get("label", "") or "").strip()
            raw_content = opt.get("content")
            if raw_content is None:
                raw_content = opt.get("text", "")
            content_md = "" if raw_content is None else str(raw_content)
        else:
            text = "" if opt is None else str(opt)
            m = _OPTION_LABEL_RE.match(text)
            if m:
                label = m.group(1).strip()
                content_md = m.group(2)
            else:
                content_md = text
        if not label:
            label = chr(ord("A") + index)
        out.append(
            {
                "id": make_option_id(index, label, content_md),
                "label": label,
                "content": markdown_to_rich_doc(content_md),
            }
        )
    return out


def adapt_legacy_question(
    *,
    q_type: Any,
    status: Any = "pending",
    content: Any,
    options: Any = None,
    answer: Any = None,
    thinking: Any = None,
    analysis: Any = None,
    summary: Any = None,
) -> dict[str, Any]:
    """把 legacy 题目 payload 转成严格 v2 QuestionCreate 字段 dict。

    返回:{content, options, answer, thinking, analysis, summary, status}(内容字段均为
    v2 对象/None;status 为字符串,答案缺失且原 status 为 pending/published 时降级为
    "draft")。无法解析选择/判断/填空答案时抛 ``LegacyQuestionError``。
    """
    qt = _q_type_value(q_type)
    status_value = _q_type_value(status)

    content_doc = markdown_to_rich_doc(None if content is None else str(content))
    if content_doc is None:
        raise LegacyQuestionError("题干为空,无法导入")

    v2_options = None
    if qt in _CHOICE_TYPES:
        v2_options = _normalize_legacy_options(options) or None

    answer_spec: Optional[dict[str, Any]] = None
    answer_present = answer is not None and (
        not isinstance(answer, str) or bool(answer.strip())
    )
    if answer_present:
        spec, needs_review = convert_answer(qt, answer, v2_options or [])
        if needs_review:
            raw = "" if answer is None else str(answer)
            raise LegacyQuestionError(
                f"{qt} 答案无法解析为 v2(原文: {raw[:80]!r}),需人工复核",
                warnings=[f"answer_unresolved:{qt}"],
            )
        answer_spec = spec
    elif status_value in {"pending", "published"}:
        # 答案缺失不阻断导入;完整性交给消费端(发布/组卷/导出)校验。
        status_value = "draft"

    return {
        "content": content_doc,
        "options": v2_options,
        "answer": answer_spec,
        "thinking": markdown_to_rich_doc(None if thinking is None else str(thinking)),
        "analysis": markdown_to_rich_doc(None if analysis is None else str(analysis)),
        "summary": markdown_to_rich_doc(None if summary is None else str(summary)),
        "status": status_value,
    }
