"""作答区默认值解析：按题型与分值推导行数，支持学科级覆盖。

历史上作答区默认值散落在 5 处创建点（组稿 ops、AI 组稿、整卷导入、前端斜杠命令、
题组节点视图），且互相矛盾（后端 4/lined、前端 3/blank）。此处收敛为唯一真源。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_subject_setting import subject_setting as crud_subject_setting
from app.models.question import QuestionType
from app.schemas.composition import ANSWER_SPACE_MAX_LINES, ANSWER_SPACE_STYLES

SUBJECT_SETTING_KEY = "answer_space_rules"


@dataclass(frozen=True)
class AnswerSpaceRule:
    """某题型的作答区推导规则。

    lines = clamp(round(score * lines_per_score), min_lines, max_lines)；
    score 缺失时退回 min_lines。enabled=False 表示该题型默认不配作答区。
    """

    enabled: bool
    min_lines: int
    lines_per_score: float
    max_lines: int
    style: str


# 代码默认值不入库；学科未定制时消费端回退到这里。
DEFAULT_RULES: Dict[str, AnswerSpaceRule] = {
    QuestionType.SINGLE_CHOICE.value: AnswerSpaceRule(False, 1, 0.0, 1, "blank"),
    QuestionType.MULTIPLE_CHOICE.value: AnswerSpaceRule(False, 1, 0.0, 1, "blank"),
    QuestionType.TRUE_FALSE.value: AnswerSpaceRule(False, 1, 0.0, 1, "blank"),
    QuestionType.FILL_IN_THE_BLANK.value: AnswerSpaceRule(True, 1, 0.5, 3, "blank"),
    QuestionType.FREE_RESPONSE.value: AnswerSpaceRule(True, 2, 0.8, 20, "lined"),
}
# 题型未知时（旧数据，或用户在没有题目上下文处手工插入）：按解答题口径推导，
# 因为显式插入作答区的场景几乎都是主观题。
FALLBACK_RULE = DEFAULT_RULES[QuestionType.FREE_RESPONSE.value]


def _coerce_rule(raw: Any, base: AnswerSpaceRule) -> AnswerSpaceRule:
    """用覆盖值逐字段收窄到合法范围；非法字段静默回退到 base，避免脏配置阻断出卷。"""
    if not isinstance(raw, dict):
        return base
    def _int(key: str, default: int) -> int:
        value = raw.get(key, default)
        if not isinstance(value, int) or isinstance(value, bool):
            return default
        return max(1, min(ANSWER_SPACE_MAX_LINES, value))

    min_lines = _int("min_lines", base.min_lines)
    max_lines = max(min_lines, _int("max_lines", base.max_lines))
    per_score = raw.get("lines_per_score", base.lines_per_score)
    if not isinstance(per_score, (int, float)) or isinstance(per_score, bool) or per_score < 0:
        per_score = base.lines_per_score
    style = raw.get("style", base.style)
    if style not in ANSWER_SPACE_STYLES:
        style = base.style
    enabled = raw.get("enabled", base.enabled)
    if not isinstance(enabled, bool):
        enabled = base.enabled
    return AnswerSpaceRule(
        enabled=enabled,
        min_lines=min_lines,
        lines_per_score=float(per_score),
        max_lines=max_lines,
        style=style,
    )


def merge_rules(override: Any) -> Dict[str, AnswerSpaceRule]:
    """把学科覆盖合并到代码默认值上（逐题型、逐字段）。"""
    if not isinstance(override, dict):
        return dict(DEFAULT_RULES)
    return {
        q_type: _coerce_rule(override.get(q_type), base)
        for q_type, base in DEFAULT_RULES.items()
    }


def rules_to_payload(rules: Dict[str, AnswerSpaceRule]) -> Dict[str, Dict[str, Any]]:
    return {q_type: asdict(rule) for q_type, rule in rules.items()}


async def load_rules(db: AsyncSession, *, subject_id: int) -> Dict[str, AnswerSpaceRule]:
    override = await crud_subject_setting.get_value(db, subject_id, SUBJECT_SETTING_KEY)
    return merge_rules(override)


def resolve_answer_space_props(
    *,
    q_type: Optional[str],
    score: Optional[float],
    rules: Optional[Dict[str, AnswerSpaceRule]] = None,
) -> Optional[Dict[str, Any]]:
    """返回作答区 props；该题型默认不配作答区时返回 None。"""
    table = rules or DEFAULT_RULES
    rule = table.get(q_type or "", FALLBACK_RULE)
    if not rule.enabled:
        return None
    if score is None or rule.lines_per_score <= 0:
        lines = rule.min_lines
    else:
        lines = round(score * rule.lines_per_score)
    lines = max(rule.min_lines, min(rule.max_lines, lines))
    return {"lines": max(1, min(ANSWER_SPACE_MAX_LINES, lines)), "style": rule.style}


def resolve_answer_space_props_or_fallback(
    *,
    q_type: Optional[str],
    score: Optional[float],
    rules: Optional[Dict[str, AnswerSpaceRule]] = None,
) -> Dict[str, Any]:
    """显式插入作答区的场景：即使题型默认不配作答区，也必须给出一组可用 props。"""
    resolved = resolve_answer_space_props(q_type=q_type, score=score, rules=rules)
    if resolved is not None:
        return resolved
    return {"lines": FALLBACK_RULE.min_lines, "style": FALLBACK_RULE.style}
