"""题目内容 v2 的集中式 JSON 编解码 + 领域校验助手。

职责(见 docs/development/question-model-v2.md §3-§6/§11):
- RichDoc 根节点校验(`validate_rich_doc`)与 ORM JSON 字符串边界的解/序列化
  (`parse_json_field` / `to_db_json`)。所有富文本槽位统一走这里,不散落。
- 跨字段领域校验(`validate_question_domain`):q_type↔answer.kind 一致、choice
  correct 引用现存 option id、非 choice options 规范化为 None、fill blankId 与
  answer blanks 顺序一一对应、option id 唯一。

设计约束:
- 本模块只处理原生 dict/list/enum,不依赖 pydantic schema,避免与 schemas 形成循环。
- 空 RichDoc → None,不存空 doc。
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from app.models.question import QuestionStatus, QuestionType

RichDoc = Dict[str, Any]

# 需要 options 的选择类题型(判断题不使用 options)。
CHOICE_TYPES = {QuestionType.SINGLE_CHOICE, QuestionType.MULTIPLE_CHOICE}

# ORM 中以 JSON 字符串存储的富文本 / AnswerSpec 列(options 是原生 JSON 列,不在此列)。
JSON_STRING_FIELDS = ("content", "answer", "thinking", "analysis", "summary")

# 填空节点可调整宽度(em)的合法区间;缺省时按默认宽度渲染。
BLANK_WIDTH_MIN_EM = 2
BLANK_WIDTH_MAX_EM = 30
BLANK_WIDTH_DEFAULT_EM = 4


# --------------------------------------------------------------------------- #
# JSON 边界:解析(ORM string → object) / 序列化(object → ORM string)
# --------------------------------------------------------------------------- #
def parse_json_field(v: Any) -> Any:
    """把 ORM 存的 JSON 字符串还原为对象;dict/list/None 原样透传。

    空串 / 纯空白 → None。非法 JSON 字符串抛 ValueError(严格 v2,不接受旧格式)。
    """
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return None
        try:
            return json.loads(s)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Invalid JSON for rich content: {exc}") from exc
    return v


def to_db_json(obj: Any) -> Optional[str]:
    """把 RichDoc / AnswerSpec 对象序列化为 ORM 存储用的 JSON 字符串;None → None。"""
    if obj is None:
        return None
    return json.dumps(obj, ensure_ascii=False)


def serialize_write_fields(data: Dict[str, Any]) -> Dict[str, Any]:
    """把写入 payload 中的富文本 / answer 字段集中序列化为 JSON 字符串。

    options 保持原生 list(走 SQLAlchemy JSON 列),不做字符串化。
    """
    out = dict(data)
    for field in JSON_STRING_FIELDS:
        if field in out:
            out[field] = to_db_json(out[field])
    return out


# --------------------------------------------------------------------------- #
# RichDoc 校验
# --------------------------------------------------------------------------- #
def validate_rich_doc(doc: Any) -> Optional[RichDoc]:
    """校验 RichDoc:None 透传;否则根节点 type 必须为 'doc' 且 content 为 list。"""
    if doc is None:
        return None
    if not isinstance(doc, dict) or doc.get("type") != "doc":
        raise ValueError("RichDoc root node type must be 'doc'")
    content = doc.get("content", [])
    if not isinstance(content, list):
        raise ValueError("RichDoc 'content' must be a list")

    def validate_node(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "image":
            attrs = node.get("attrs") or {}
            for name in ("width", "height"):
                value = attrs.get(name)
                if value is None:
                    continue
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or float(value) <= 0
                    or float(value) > 20_000
                ):
                    raise ValueError(
                        f"image {name} must be a finite number between 0 and 20000 px"
                    )
            align = attrs.get("align")
            if align is not None and align not in ("left", "center", "right"):
                raise ValueError("image align must be one of left/center/right")
        if node.get("type") == "blank":
            # widthEm 可选;缺省由渲染侧按默认宽度处理。给定时必须是 2..30 的有限数字。
            value = (node.get("attrs") or {}).get("widthEm")
            if value is not None and (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
                or float(value) < BLANK_WIDTH_MIN_EM
                or float(value) > BLANK_WIDTH_MAX_EM
            ):
                raise ValueError(
                    f"blank widthEm must be a finite number between "
                    f"{BLANK_WIDTH_MIN_EM} and {BLANK_WIDTH_MAX_EM}"
                )
        for child in node.get("content") or []:
            validate_node(child)

    validate_node(doc)
    return doc


def collect_blank_ids(doc: Optional[RichDoc]) -> List[str]:
    """按出现顺序收集 RichDoc 中所有 blank 节点的 blankId。"""
    ids: List[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if node.get("type") == "blank":
            blank_id = (node.get("attrs") or {}).get("blankId")
            if blank_id is not None:
                ids.append(blank_id)
        for child in node.get("content") or []:
            walk(child)

    if doc:
        walk(doc)
    return ids


# --------------------------------------------------------------------------- #
# options 规范化
# --------------------------------------------------------------------------- #
def normalize_options(q_type: Optional[QuestionType], options: Any) -> Optional[List[Dict[str, Any]]]:
    """非 choice 题型的 options 规范化为 None;choice 题型透传(空 list → None)。"""
    if q_type is not None and q_type not in CHOICE_TYPES:
        return None
    if not options:
        return None
    return options


# --------------------------------------------------------------------------- #
# 领域校验(跨字段)
# --------------------------------------------------------------------------- #
def validate_question_domain(
    *,
    q_type: Optional[QuestionType],
    status: Optional[QuestionStatus],
    content: Any,
    options: Any,
    answer: Any,
    partial: bool = False,
    require_complete: bool = False,
) -> None:
    """跨字段领域校验(见 PRD §11)。

    partial=True(更新 payload):缺失字段跳过相关跨字段检查,避免误拒。
    draft 允许题干/答案暂不完整;pending/published 或 require_complete=True 时执行
    可用于审核、发布、组卷的完整性校验。partial=True 时只校验本次可判定的结构约束。
    """
    must_be_complete = require_complete or status in {
        QuestionStatus.PENDING,
        QuestionStatus.PUBLISHED,
    }

    # 1. 题干是题目记录的最小内容;答案完整性才随生命周期变化。
    if content is None and not partial:
        raise ValueError("content is required")
    if content is not None:
        validate_rich_doc(content)

    # 2. option id 唯一(有 options 就校验)。
    if options:
        ids = [o.get("id") for o in options]
        if any(not oid for oid in ids):
            raise ValueError("每个 option 必须有非空 id")
        if len(set(ids)) != len(ids):
            raise ValueError("option id 必须唯一")

    # 3. 非 choice 题型不得携带 options(规范化后应为 None)。
    if q_type is not None and q_type not in CHOICE_TYPES and options:
        raise ValueError(f"{q_type.value} 题型不应包含 options")

    if answer is None:
        if must_be_complete and not partial:
            raise ValueError("answer is required")
        return

    kind = answer.get("kind")

    # 4. answer.kind 与 q_type 一致(两者都在时才校验)。
    if q_type is not None and kind != q_type.value:
        raise ValueError(f"answer.kind '{kind}' 与 q_type '{q_type.value}' 不一致")

    # 5. choice:correct 引用的 id 必须存在于 options。
    #    partial 且 options 未提供(None)时无从校验,跳过(留待 CRUD 合并后终检)。
    if kind in ("single_choice", "multiple_choice") and not (partial and options is None):
        option_ids = {o.get("id") for o in (options or [])}
        if kind == "single_choice":
            correct = answer.get("correct")
            if correct and correct not in option_ids:
                raise ValueError(f"single_choice correct '{correct}' 不在 options 中")
            if must_be_complete and not correct:
                raise ValueError("single_choice correct 不能为空")
        else:
            correct_ids = answer.get("correct", [])
            for correct in correct_ids:
                if correct not in option_ids:
                    raise ValueError(f"multiple_choice correct '{correct}' 不在 options 中")
            if must_be_complete and not correct_ids:
                raise ValueError("multiple_choice correct 不能为空")

    # 6. fill:题干含 blank 节点时,blankId 与 answer blanks id 按顺序一一对应。
    if kind == "fill_in_the_blank" and content is not None:
        blank_ids = collect_blank_ids(content)
        if blank_ids and (must_be_complete or answer.get("blanks")):
            answer_ids = [b.get("id") for b in answer.get("blanks", [])]
            if blank_ids != answer_ids:
                raise ValueError("题干 blank 节点的 blankId 必须与 answer blanks 顺序一一对应")

    if kind == "fill_in_the_blank" and must_be_complete:
        blanks = answer.get("blanks", [])
        if not blanks:
            raise ValueError("fill_in_the_blank blanks 不能为空")
        if any(not blank.get("accept") or any(item is None for item in blank.get("accept", [])) for blank in blanks):
            raise ValueError("blank accept 必须是非空的 RichDoc 列表")

    if kind == "free_response" and must_be_complete and answer.get("reference") is None:
        raise ValueError("free_response reference 不能为空")


def validate_question_for_exam(question: Any) -> None:
    """校验 ORM Question 是否可用于组卷/导出，不依赖题目当前生命周期状态。"""
    q_type = question.q_type
    if isinstance(q_type, str):
        q_type = QuestionType(q_type)
    validate_question_domain(
        q_type=q_type,
        status=None,
        content=parse_json_field(question.content),
        options=question.options,
        answer=parse_json_field(question.answer),
        partial=False,
        require_complete=True,
    )
