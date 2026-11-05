"""调用 AI 拆解一段题干:组装提示词 → 调用模型 → 解析与校验 → 体检 → 必要时带着问题重试一次。

本模块不写数据库;结果(``Draft``)由 ``service.save_draft`` 落库。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.crud_subject_prompt import subject_prompt as crud_subject_prompt
from app.models.question_structure import StructFacet, StructType, StructTypeKind
from app.models.subject import Subject
from app.services.prompt_utils import apply_output_language, render_subject_prompt
from app.services.prompts import get_default_prompt

from . import types as type_svc
from .check import CheckItem, Report, check_structure
from .params import SLOT_KINDS, DraftParam, check_params, parse_domain

logger = logging.getLogger(__name__)

PROMPT_KEY = "AI_STRUCT_DECOMPOSE_PROMPT"
# 默认提示词的版本;规则改动时递增,便于按版本比较拆解质量。学科自定义的提示词记为 "custom"。
PROMPT_VERSION = "v3"
CUSTOM_PROMPT_VERSION = "custom"
# 首次结果体检有 error 时,带着问题清单重试的次数。
RETRY_ON_CHECK_ERRORS = 1


class ModelNotConfigured(Exception):
    """没有可用的文本模型:job 应以 model 原因暂停,等管理员配置后自动恢复。"""


@dataclass
class DraftElement:
    """一条待落库的条件。"""

    content: str
    source: Optional[str] = None
    type_id: Optional[int] = None
    type_hint: Optional[str] = None
    facet: Optional[str] = None
    span: Optional[tuple] = None
    # 引用材料拆解中的条件(共享),此时没有 span。
    ref_element_id: Optional[int] = None


@dataclass
class DraftAsk:
    """一条待落库的设问;``depends_on`` 是本拆解中条件的下标。"""

    content: str
    source: Optional[str] = None
    type_id: Optional[int] = None
    type_hint: Optional[str] = None
    span: Optional[tuple] = None
    depends_on: List[int] = field(default_factory=list)


@dataclass
class DraftGroup:
    """一个待落库的元素组;``element_indices`` 是本拆解中条件的下标。"""

    name: str
    element_indices: List[int]
    description: Optional[str] = None
    replaceable: bool = True


@dataclass
class Draft:
    """一次拆解的结果(尚未落库)。"""

    elements: List[DraftElement]
    asks: List[DraftAsk]
    report: Report
    params: List[DraftParam] = field(default_factory=list)
    groups: List[DraftGroup] = field(default_factory=list)
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    provider_id: Optional[int] = None


@dataclass(frozen=True)
class SharedCondition:
    """材料拆解中可被小题引用的条件。"""

    element_id: int
    content: str


# region AI 输出的宽松解析模型(字段缺失、类型不对都尽量容忍,真正的错误交给体检)

class _AIParam(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    value: str = ""
    kind: Optional[str] = None
    occurrence: int = 1
    domain: Optional[Dict[str, Any]] = None

    @field_validator("name", "value", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("occurrence", mode="before")
    @classmethod
    def _occurrence(cls, value: Any) -> int:
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return 1

    @field_validator("domain", mode="before")
    @classmethod
    def _domain(cls, value: Any) -> Optional[Dict[str, Any]]:
        return value if isinstance(value, dict) else None


class _AICondition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source: str = ""
    content: str = ""
    type: Optional[str] = None
    type_hint: Optional[str] = None
    facet: Optional[str] = None
    params: List[_AIParam] = Field(default_factory=list)

    @field_validator("params", mode="before")
    @classmethod
    def _params(cls, value: Any) -> List[Any]:
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    @field_validator("source", "content", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return "" if value is None else str(value)

    @field_validator("type", "type_hint", "facet", mode="before")
    @classmethod
    def _optional_text(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return None if text.lower() in ("", "null", "none") else text


class _AIAsk(_AICondition):
    depends_on: List[int] = Field(default_factory=list)
    material_refs: List[int] = Field(default_factory=list)

    @field_validator("depends_on", "material_refs", mode="before")
    @classmethod
    def _indices(cls, value: Any) -> List[int]:
        if not isinstance(value, list):
            return []
        out: List[int] = []
        for item in value:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out


class _AIOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conditions: List[_AICondition] = Field(default_factory=list)
    asks: List[_AIAsk] = Field(default_factory=list)

# endregion


# region 公共函数

async def decompose(
    db: AsyncSession,
    *,
    stem_text: str,
    subject_id: Optional[int],
    user_id: Optional[int],
    shared: Sequence[SharedCondition] = (),
) -> Draft:
    """调用 AI 拆解题干并体检。体检有 error 时带着问题清单重试一次,返回问题更少的那次。

    :raises ModelNotConfigured: 没有可用的文本模型。
    :raises Exception: AI 调用错误原样抛出,由调用方按 ai_errors 分类(暂停 / 失败)。
    """
    from app.services.ai_errors import with_ai_retry
    from app.services.ai_provider import get_ai_provider
    from app.services.ai_resolver import resolve_model

    resolved = await resolve_model(db, user_id=user_id, purpose="text")
    if resolved is None:
        raise ModelNotConfigured()
    provider = get_ai_provider(resolved.interface_type)
    types: List[StructType] = []
    if subject_id is not None:
        await type_svc.ensure_roots(db, subject_id)
        types = await type_svc.list_types(db, subject_id)
    system, prompt_version = await build_system_prompt(db, subject_id=subject_id, types=types)

    best: Optional[Draft] = None
    feedback: List[str] = []
    for attempt in range(RETRY_ON_CHECK_ERRORS + 1):
        user = build_user_message(stem_text, shared, feedback)
        raw = await with_ai_retry(lambda: provider.generate_json(system, user, resolved.config))
        draft = parse_output(raw, stem_text=stem_text, types=types, shared=shared)
        draft.model = resolved.model.name
        draft.prompt_version = prompt_version
        draft.provider_id = resolved.provider.id
        if best is None or draft.report.error_count < best.report.error_count:
            best = draft
        if draft.report.ok:
            break
        if attempt == RETRY_ON_CHECK_ERRORS:
            # 重试次数已用完:保留问题最少的一次,交给人工审核。
            logger.info("Structure decomposition still has %d error(s) after %d attempt(s); keeping the best result", best.report.error_count, attempt + 1)
            break
        feedback = describe_errors(draft)
        logger.info("Structure decomposition attempt %d has %d error(s); retrying", attempt + 1, draft.report.error_count)
    assert best is not None
    return best


async def build_system_prompt(
    db: AsyncSession, *, subject_id: Optional[int], types: Sequence[StructType]
) -> tuple[str, str]:
    """系统提示词(学科覆盖 → 代码默认),并注入学科启用的元素类型。返回 (提示词, 版本)。"""
    subject = await db.get(Subject, subject_id) if subject_id else None
    override = await crud_subject_prompt.get_value(db, subject_id, PROMPT_KEY) if subject_id else None
    template = override if override is not None else get_default_prompt(PROMPT_KEY)
    prompt = render_subject_prompt(template, subject) or ""
    conditions = type_svc.tree_text(types, StructTypeKind.CONDITION) or "(none yet)"
    asks = type_svc.tree_text(types, StructTypeKind.ASK) or "(none yet)"
    prompt = prompt.replace("{condition_types}", conditions).replace("{ask_types}", asks)
    prompt = apply_output_language(prompt, "extract")
    return prompt, CUSTOM_PROMPT_VERSION if override is not None else PROMPT_VERSION


def build_user_message(stem_text: str, shared: Sequence[SharedCondition], feedback: Sequence[str]) -> str:
    """本次输入:题干、可引用的材料条件、上一次结果的问题清单。"""
    parts = ["## Stem\n<<<\n" + stem_text + "\n>>>"]
    if shared:
        listed = "\n".join(f"{index}. {item.content}" for index, item in enumerate(shared))
        parts.append("## Shared material conditions (already extracted; cite by index, do not repeat)\n" + listed)
    if feedback:
        parts.append("## Problems in your previous answer - fix them\n" + "\n".join(f"- {line}" for line in feedback))
    return "\n\n".join(parts)


def parse_output(
    raw: Any,
    *,
    stem_text: str,
    types: Sequence[StructType],
    shared: Sequence[SharedCondition] = (),
) -> Draft:
    """把模型输出转成 Draft:类型 code → id,设问依赖与材料引用 → 下标,并体检、定位原文。

    模型输出整体不是对象时抛 ``ValueError``(由 ai_errors 归为文档类错误)。
    """
    if isinstance(raw, list):
        raw = {"conditions": raw}
    if not isinstance(raw, dict):
        raise ValueError("Decomposition output is not a JSON object")
    if "conditions" not in raw and "elements" in raw:
        raw = {**raw, "conditions": raw["elements"]}
    output = _AIOutput.model_validate(raw)

    by_code = {
        (t.kind, t.code): t.id for t in types if t.status == "active"
    }
    elements: List[DraftElement] = []
    params: List[DraftParam] = []
    for item in output.conditions:
        if not item.content.strip() and not item.source.strip():
            continue
        type_id, hint = _resolve_type(by_code, StructTypeKind.CONDITION, item.type, item.type_hint)
        facet = item.facet if item.facet in {f.value for f in StructFacet} else None
        params.extend(_params_of(item, "element", len(elements)))
        elements.append(DraftElement(
            content=(item.content or item.source).strip(),
            source=item.source.strip() or None,
            type_id=type_id,
            type_hint=hint,
            facet=facet,
        ))

    # 材料条件被设问引用时,在本拆解中各建一条引用条件(只建一次),追加在题干条件之后。
    shared_index: Dict[int, int] = {}
    asks: List[DraftAsk] = []
    for item in output.asks:
        if not item.content.strip() and not item.source.strip():
            continue
        type_id, hint = _resolve_type(by_code, StructTypeKind.ASK, item.type, item.type_hint)
        depends = [i for i in item.depends_on if 0 <= i < len(output.conditions)]
        # 输出里跳过了空条件,下标需要重新对齐。
        depends = [_realign(output.conditions, i) for i in depends]
        depends = [i for i in depends if i is not None]
        for ref in item.material_refs:
            if not 0 <= ref < len(shared):
                continue
            if ref not in shared_index:
                shared_index[ref] = len(elements)
                elements.append(DraftElement(content=shared[ref].content, ref_element_id=shared[ref].element_id))
            depends.append(shared_index[ref])
        params.extend(_params_of(item, "ask", len(asks)))
        asks.append(DraftAsk(
            content=(item.content or item.source).strip(),
            source=item.source.strip() or None,
            type_id=type_id,
            type_hint=hint,
            depends_on=sorted(set(depends)),
        ))

    report = run_check(stem_text, elements, asks, shared, params)
    return Draft(elements=elements, asks=asks, report=report, params=params)


def run_check(
    stem_text: str,
    elements: Sequence[DraftElement],
    asks: Sequence[DraftAsk],
    shared: Sequence[SharedCondition] = (),
    params: Sequence[DraftParam] = (),
) -> Report:
    """体检并把定位出的原文区间写回各条目与参数。"""
    report = check_structure(
        stem_text,
        [
            CheckItem(e.content, source=e.source, start=_start(e.span), end=_end(e.span), shared=e.ref_element_id is not None)
            for e in elements
        ],
        [CheckItem(a.content, source=a.source, start=_start(a.span), end=_end(a.span)) for a in asks],
        shared_texts=[s.content for s in shared],
    )
    for element, span in zip(elements, report.element_spans):
        element.span = span
    for ask, span in zip(asks, report.ask_spans):
        ask.span = span
    if params:
        report.issues.extend(check_params(stem_text, params, report.element_spans, report.ask_spans))
    return report


def describe_errors(draft: Draft) -> List[str]:
    """把体检 error 写成给模型看的问题清单(英文)。"""
    lines: List[str] = []
    for issue in draft.report.issues:
        if issue.severity != "error":
            continue
        label = f"{issue.target} {issue.index}" if issue.target is not None else "stem"
        if issue.code == "span_not_found":
            lines.append(f"{label}: `source` is not an exact quote of the stem: {json.dumps(issue.detail, ensure_ascii=False)}")
        elif issue.code == "dangling_symbol":
            lines.append(f"{label}: symbol `{issue.detail}` is used by an ask but no condition introduces it (a condition is probably missing)")
        elif issue.code == "duplicate":
            lines.append(f"{label}: duplicates another condition")
        elif issue.code == "param_not_found":
            lines.append(f"{label}: parameter value `{issue.detail}` is not an exact, standalone part of its item's `source`")
        elif issue.code in ("param_outside_owner", "param_overlap", "param_value_mismatch"):
            lines.append(f"{label}: {issue.message.lower()}; give each parameter a distinct value quoted from its own item")
        else:
            lines.append(f"{label}: {issue.message}")
    return lines

# endregion


# region 内部实现

def _resolve_type(
    by_code: Dict[tuple, int], kind: StructTypeKind, code: Optional[str], hint: Optional[str]
) -> tuple[Optional[int], Optional[str]]:
    """类型 code → id;未知 code 不丢弃,作为 type_hint 留给归纳。"""
    if code and (kind.value, code) in by_code:
        return by_code[(kind.value, code)], (hint[:255] if hint else None)
    fallback = hint or code
    return None, (fallback[:255] if fallback else None)


def _params_of(item: _AICondition, owner: str, owner_index: int) -> List[DraftParam]:
    """条目下 AI 标出的参数 → DraftParam(名称或值为空的丢弃)。"""
    out: List[DraftParam] = []
    for param in item.params:
        if not param.value:
            continue
        out.append(DraftParam(
            name=(param.name or param.value)[:64],
            value=param.value,
            owner=owner,
            owner_index=owner_index,
            slot_kind=param.kind if param.kind in SLOT_KINDS else "numeric",
            occurrence=param.occurrence,
            domain=parse_domain(param.domain),
        ))
    return out


def _realign(conditions: Sequence[_AICondition], index: int) -> Optional[int]:
    """模型给出的条件下标 → 跳过空条件后的下标。"""
    if not (conditions[index].content.strip() or conditions[index].source.strip()):
        return None
    return sum(1 for c in conditions[:index] if c.content.strip() or c.source.strip())


def _start(span: Optional[tuple]) -> Optional[int]:
    return span[0] if span else None


def _end(span: Optional[tuple]) -> Optional[int]:
    return span[1] if span else None

# endregion
