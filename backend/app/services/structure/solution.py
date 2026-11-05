"""解答结构(规格 §12.3 N7):把解答拆成步骤,并据此计算思维量难度。

前提:题目有**已采纳且未过期**的题干拆解——步骤引用的条件 / 设问就是它的条目。

- **拆解**(``solution.decompose`` 任务):题干条件(C1…)、设问(Q1…)、参考解答(题目解析;没有时让
  AI 自行解答)与方法类型树交给 AI,输出步骤;体检有 error 时带着问题重试一次;存为待审快照。
- **体检**:步骤目标不能为空;引用的条件 / 设问必须存在;只能引用前面的步骤;每个设问都要有步骤
  作答;未归类方法只记 warning。
- **审核**:同一题、同一种解法(``solution_no``)最多一条已采纳;采纳后重算题目的思维量难度。
- **思维量**:一次解答 = 各步骤方法类型权重之和(未归类记 1);题目 = 已采纳解法中的最小值。
  方法类型的权重变化时,用到它的已采纳解答一并重算。
- **复核**:题干拆解被取代或题目内容修改后,解答显示为需复核(``stale``),与题干拆解的过期判断同理。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Invalid, NotFound
from app.core.api_errors import ErrorCode
from app.crud.crud_subject_prompt import subject_prompt as crud_subject_prompt
from app.models.import_task import ImportPauseReason
from app.models.job import ACTIVE_JOB_STATUSES, Job, JobPriority
from app.models.question import Question
from app.models.question_structure import (
    StructOrigin,
    StructRun,
    StructRunState,
    StructTargetType,
    StructType,
    StructTypeKind,
)
from app.models.solution_structure import (
    MisconceptionSource,
    SolutionLinkRole,
    SolutionMisconception,
    SolutionRun,
    SolutionStep,
    SolutionStepLink,
)
from app.models.subject import Subject
from app.services.jobs import JobContext, JobHandler, JobStopped, register_handler
from app.services.prompt_utils import apply_output_language, render_subject_prompt
from app.services.prompts import get_default_prompt

from . import settings as struct_settings
from . import types as type_svc
from .check import Issue, Report
from .text import rich_doc_to_stem_text

logger = logging.getLogger(__name__)

JOB_TYPE = "solution.decompose"
PROMPT_KEY = "AI_SOLUTION_DECOMPOSE_PROMPT"
PROMPT_VERSION = "v1"
CUSTOM_PROMPT_VERSION = "custom"
RETRY_ON_CHECK_ERRORS = 1
ERROR_NEEDS_STEM = "needs_stem"

_REF_RE = re.compile(r"^\s*([CQS])\s*(\d+)\s*$", re.IGNORECASE)


@dataclass
class DraftStep:
    """一个待落库的步骤。条件 / 设问用题干拆解中的 id,前序步骤用本次解答中的下标。"""

    goal: str
    result: Optional[str] = None
    method_type_id: Optional[int] = None
    method_hint: Optional[str] = None
    is_key: bool = False
    uses_elements: List[int] = field(default_factory=list)
    uses_asks: List[int] = field(default_factory=list)
    uses_steps: List[int] = field(default_factory=list)
    answers: List[int] = field(default_factory=list)
    misconceptions: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class SolutionDraft:
    """一次解答拆解的结果(尚未落库)。"""

    steps: List[DraftStep]
    report: Report
    solution_text: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    provider_id: Optional[int] = None


@dataclass
class StemContext:
    """解答拆解所依据的题干:已采纳的题干拆解。"""

    run: StructRun
    element_ids: List[int]
    ask_ids: List[int]


# region AI 输出的宽松解析模型

class _AIMisconception(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = ""
    source: Optional[str] = None

    @field_validator("description", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()


class _AIStep(BaseModel):
    model_config = ConfigDict(extra="ignore")

    goal: str = ""
    result: Optional[str] = None
    method: Optional[str] = None
    method_hint: Optional[str] = None
    key: bool = False
    uses: List[str] = Field(default_factory=list)
    answers: List[str] = Field(default_factory=list)
    misconceptions: List[_AIMisconception] = Field(default_factory=list)

    @field_validator("goal", mode="before")
    @classmethod
    def _goal(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("result", "method", "method_hint", mode="before")
    @classmethod
    def _optional(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return None if text.lower() in ("", "null", "none") else text

    @field_validator("key", mode="before")
    @classmethod
    def _key(cls, value: Any) -> bool:
        return value is True or str(value).lower() == "true"

    @field_validator("uses", "answers", mode="before")
    @classmethod
    def _refs(cls, value: Any) -> List[str]:
        return [str(item) for item in value] if isinstance(value, list) else []

    @field_validator("misconceptions", mode="before")
    @classmethod
    def _misconceptions(cls, value: Any) -> List[Any]:
        if not isinstance(value, list):
            return []
        return [item if isinstance(item, dict) else {"description": str(item)} for item in value]


class _AIOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    steps: List[_AIStep] = Field(default_factory=list)

# endregion


# region 题干依据

async def stem_context(db: AsyncSession, question: Question) -> StemContext:
    """题目已采纳、未过期的题干拆解;没有时抛 Invalid(需要先完成题干拆解)。"""
    from . import service as struct_service

    run = await struct_service.accepted_run(db, StructTargetType.QUESTION.value, question.id)
    if run is None or (run.source_revision or 1) != (question.content_revision or 1):
        raise Invalid("Accept an up-to-date stem decomposition first", ErrorCode.STRUCTURE_SOLUTION_NEEDS_STEM)
    return StemContext(run=run, element_ids=[e.id for e in run.elements], ask_ids=[a.id for a in run.asks])


def reference_solution(question: Question) -> Optional[str]:
    """参考解答:题目解析的纯文本(公式保留 $...$);没有解析时为空。"""
    text = rich_doc_to_stem_text(question.analysis) if question.analysis else ""
    return text or None

# endregion


# region 体检

def check_steps(steps: Sequence[DraftStep], element_ids: Sequence[int], ask_ids: Sequence[int]) -> Report:
    """体检解答步骤,返回报告(只有 issues 有意义)。"""
    report = Report()
    elements, asks = set(element_ids), set(ask_ids)
    answered: set = set()
    for index, step in enumerate(steps):
        if not step.goal.strip():
            report.issues.append(_issue("empty", "Step goal is empty", index))
        unknown = [i for i in step.uses_elements if i not in elements] + [
            i for i in step.uses_asks + step.answers if i not in asks
        ]
        if unknown:
            report.issues.append(_issue("unknown_ref", "Step references a missing condition or ask", index, str(unknown)))
        bad = [i for i in step.uses_steps if not 0 <= i < index]
        if bad:
            report.issues.append(_issue("forward_ref", "Step references itself or a later step", index, str([i + 1 for i in bad])))
        if step.method_type_id is None:
            report.issues.append(Issue(
                code="no_method", severity="warning", message="Step method is not classified",
                target="step", index=index, detail=step.method_hint or "",
            ))
        answered.update(step.answers)
    for ordinal, ask_id in enumerate(ask_ids):
        if ask_id not in answered:
            report.issues.append(Issue(
                code="ask_unanswered", severity="error", message="No step answers this ask",
                target=None, index=None, detail=f"Q{ordinal + 1}",
            ))
    return report


def describe_errors(report: Report) -> List[str]:
    """体检 error → 给模型看的问题清单(英文)。"""
    lines = []
    for issue in report.issues:
        if issue.severity != "error":
            continue
        label = f"step {issue.index + 1}" if issue.index is not None else "solution"
        if issue.code == "ask_unanswered":
            lines.append(f"{issue.detail} is not answered by any step (list it in `answers`)")
        elif issue.code == "forward_ref":
            lines.append(f"{label} uses later steps {issue.detail}; only earlier steps can be used")
        elif issue.code == "unknown_ref":
            lines.append(f"{label} references unknown items; use only the given C/Q numbers")
        else:
            lines.append(f"{label}: {issue.message}")
    return lines

# endregion


# region 调用 AI

async def decompose_solution(
    db: AsyncSession, question: Question, stem: StemContext, *, user_id: Optional[int]
) -> SolutionDraft:
    """调用 AI 拆解解答并体检;有 error 时带着问题重试一次,返回问题更少的那次。

    :raises ModelNotConfigured: 没有可用的文本模型。
    """
    from app.services.ai_errors import with_ai_retry
    from app.services.ai_provider import get_ai_provider
    from app.services.ai_resolver import resolve_model

    from .decompose import ModelNotConfigured

    resolved = await resolve_model(db, user_id=user_id, purpose="text")
    if resolved is None:
        raise ModelNotConfigured()
    provider = get_ai_provider(resolved.interface_type)
    types: List[StructType] = []
    if question.subject_id is not None:
        await type_svc.ensure_roots(db, question.subject_id)
        types = await type_svc.list_types(db, question.subject_id)
    system, prompt_version = await build_system_prompt(db, subject_id=question.subject_id, types=types)
    solution_text = reference_solution(question)

    best: Optional[SolutionDraft] = None
    feedback: List[str] = []
    for attempt in range(RETRY_ON_CHECK_ERRORS + 1):
        user = build_user_message(stem, solution_text, feedback)
        raw = await with_ai_retry(lambda: provider.generate_json(system, user, resolved.config))
        draft = parse_output(raw, stem=stem, types=types)
        draft.solution_text = solution_text
        draft.model = resolved.model.name
        draft.prompt_version = prompt_version
        draft.provider_id = resolved.provider.id
        if best is None or draft.report.error_count < best.report.error_count:
            best = draft
        if draft.report.ok or attempt == RETRY_ON_CHECK_ERRORS:
            break
        feedback = describe_errors(draft.report)
    assert best is not None
    return best


async def build_system_prompt(
    db: AsyncSession, *, subject_id: Optional[int], types: Sequence[StructType]
) -> Tuple[str, str]:
    subject = await db.get(Subject, subject_id) if subject_id else None
    override = await crud_subject_prompt.get_value(db, subject_id, PROMPT_KEY) if subject_id else None
    template = override if override is not None else get_default_prompt(PROMPT_KEY)
    prompt = render_subject_prompt(template, subject) or ""
    methods = type_svc.tree_text(types, StructTypeKind.METHOD) or "(none yet)"
    prompt = prompt.replace("{method_types}", methods)
    prompt = apply_output_language(prompt, "extract")
    return prompt, CUSTOM_PROMPT_VERSION if override is not None else PROMPT_VERSION


def build_user_message(stem: StemContext, solution_text: Optional[str], feedback: Sequence[str]) -> str:
    conditions = "\n".join(f"C{i + 1}. {e.content}" for i, e in enumerate(stem.run.elements)) or "(none)"
    asks = "\n".join(f"Q{i + 1}. {a.content}" for i, a in enumerate(stem.run.asks)) or "(none)"
    parts = [
        "## Stem\n<<<\n" + stem.run.stem_text + "\n>>>",
        "## Conditions\n" + conditions,
        "## Asks\n" + asks,
        "## Reference solution\n" + ("<<<\n" + solution_text + "\n>>>" if solution_text else "(none - solve it yourself)"),
    ]
    if feedback:
        parts.append("## Problems in your previous answer - fix them\n" + "\n".join(f"- {line}" for line in feedback))
    return "\n\n".join(parts)


def parse_output(raw: Any, *, stem: StemContext, types: Sequence[StructType]) -> SolutionDraft:
    """模型输出 → 步骤(C/Q/S 编号换成 id / 下标),并体检。整体不是对象时抛 ValueError。"""
    if isinstance(raw, list):
        raw = {"steps": raw}
    if not isinstance(raw, dict):
        raise ValueError("Solution output is not a JSON object")
    output = _AIOutput.model_validate(raw)
    by_code = {t.code: t.id for t in types if t.kind == StructTypeKind.METHOD.value and t.status == "active"}
    steps: List[DraftStep] = []
    for item in output.steps:
        if not item.goal and not item.result:
            continue
        step = DraftStep(
            goal=item.goal or (item.result or ""),
            result=item.result,
            method_type_id=by_code.get(item.method) if item.method else None,
            method_hint=((item.method_hint or (item.method if item.method not in by_code else None)) or None),
            is_key=item.key,
        )
        if step.method_hint:
            step.method_hint = step.method_hint[:255]
        for ref in item.uses:
            kind, number = _ref(ref)
            if kind == "C" and 0 < number <= len(stem.element_ids):
                step.uses_elements.append(stem.element_ids[number - 1])
            elif kind == "Q" and 0 < number <= len(stem.ask_ids):
                step.uses_asks.append(stem.ask_ids[number - 1])
            elif kind == "S" and number > 0:
                step.uses_steps.append(number - 1)
        for ref in item.answers:
            kind, number = _ref(ref)
            if kind == "Q" and 0 < number <= len(stem.ask_ids):
                step.answers.append(stem.ask_ids[number - 1])
        step.misconceptions = [
            (m.description, m.source if m.source in {s.value for s in MisconceptionSource} else MisconceptionSource.DISTRACTOR.value)
            for m in item.misconceptions if m.description
        ]
        steps.append(step)
    return SolutionDraft(steps=steps, report=check_steps(steps, stem.element_ids, stem.ask_ids))

# endregion


# region 保存、审核与思维量

async def save_draft(
    db: AsyncSession,
    question: Question,
    stem: StemContext,
    draft: SolutionDraft,
    *,
    solution_no: int = 1,
    origin: str = StructOrigin.AI.value,
    job_id: Optional[int] = None,
    created_by: Optional[int] = None,
) -> SolutionRun:
    """保存为待审快照(flush,不提交)。同一题、同一种解法此前的待审快照被取代。"""
    await db.execute(
        update(SolutionRun)
        .where(
            SolutionRun.question_id == question.id,
            SolutionRun.solution_no == solution_no,
            SolutionRun.state == StructRunState.DRAFT.value,
        )
        .values(state=StructRunState.SUPERSEDED.value, updated_at=datetime.utcnow())
        .execution_options(synchronize_session=False)
    )
    weights = await _method_weights(db, question.subject_id)
    run = SolutionRun(
        question_id=question.id,
        subject_id=question.subject_id,
        stem_run_id=stem.run.id,
        solution_no=solution_no,
        source_revision=question.content_revision or 1,
        solution_text=draft.solution_text,
        origin=origin,
        model=draft.model,
        prompt_version=draft.prompt_version,
        job_id=job_id,
        state=StructRunState.DRAFT.value,
        thinking_load=thinking_load([s.method_type_id for s in draft.steps], weights),
        check_report=json.dumps(draft.report.to_dict(), ensure_ascii=False),
        check_errors=draft.report.error_count,
        check_warnings=draft.report.warning_count,
        created_by=created_by,
    )
    db.add(run)
    await db.flush()
    saved: List[SolutionStep] = []
    for ordinal, item in enumerate(draft.steps):
        step = SolutionStep(
            run_id=run.id,
            ordinal=ordinal,
            goal=item.goal,
            result=item.result,
            method_type_id=item.method_type_id,
            method_hint=item.method_hint,
            is_key=item.is_key,
        )
        db.add(step)
        await db.flush()
        saved.append(step)
        for element_id in dict.fromkeys(item.uses_elements):
            db.add(SolutionStepLink(step_id=step.id, role=SolutionLinkRole.USES.value, element_id=element_id))
        for ask_id in dict.fromkeys(item.uses_asks):
            db.add(SolutionStepLink(step_id=step.id, role=SolutionLinkRole.USES.value, ask_id=ask_id))
        for index in dict.fromkeys(item.uses_steps):
            if 0 <= index < ordinal:
                db.add(SolutionStepLink(step_id=step.id, role=SolutionLinkRole.USES.value, prev_step_id=saved[index].id))
        for ask_id in dict.fromkeys(item.answers):
            db.add(SolutionStepLink(step_id=step.id, role=SolutionLinkRole.ANSWERS.value, ask_id=ask_id))
        for description, source in item.misconceptions:
            db.add(SolutionMisconception(step_id=step.id, description=description, source=source))
    await db.flush()
    return run


async def save_human(
    db: AsyncSession,
    question: Question,
    *,
    steps: Sequence[Dict[str, Any]],
    solution_no: int,
    user_id: Optional[int],
    origin: str = StructOrigin.HUMAN.value,
) -> SolutionRun:
    """保存人工修改的解答,新建一条快照。

    ``steps`` 的每项:goal(必填)、result、method_type_id、method_hint、is_key、uses_elements /
    uses_asks / answers(题干拆解中的 id)、uses_steps(本次解答中的下标)、misconceptions
    ([{description, source}])。
    """
    stem = await stem_context(db, question)
    allowed = await _method_type_ids(db, question.subject_id)
    drafts: List[DraftStep] = []
    for item in steps:
        goal = str(item.get("goal") or "").strip()
        if not goal:
            raise Invalid("Step goal is required", ErrorCode.STRUCTURE_INVALID_ITEM)
        method = item.get("method_type_id")
        if method is not None and int(method) not in allowed:
            raise Invalid("Invalid method type", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
        drafts.append(DraftStep(
            goal=goal,
            result=(str(item.get("result") or "").strip() or None),
            method_type_id=int(method) if method is not None else None,
            method_hint=(str(item.get("method_hint") or "").strip()[:255] or None),
            is_key=bool(item.get("is_key")),
            uses_elements=[int(i) for i in item.get("uses_elements") or []],
            uses_asks=[int(i) for i in item.get("uses_asks") or []],
            uses_steps=[int(i) for i in item.get("uses_steps") or []],
            answers=[int(i) for i in item.get("answers") or []],
            misconceptions=[
                (str(m.get("description") or "").strip(), m.get("source") or MisconceptionSource.DISTRACTOR.value)
                for m in item.get("misconceptions") or []
                if isinstance(m, dict) and str(m.get("description") or "").strip()
            ],
        ))
    report = check_steps(drafts, stem.element_ids, stem.ask_ids)
    draft = SolutionDraft(steps=drafts, report=report, solution_text=reference_solution(question))
    return await save_draft(db, question, stem, draft, solution_no=solution_no, origin=origin, created_by=user_id)


async def review(db: AsyncSession, run: SolutionRun, *, accept: bool, reviewer_id: Optional[int]) -> SolutionRun:
    """采纳或驳回一条待审解答(flush,不提交);采纳后重算题目的思维量难度。"""
    if run.state != StructRunState.DRAFT.value:
        raise Invalid("Only draft solutions can be reviewed", ErrorCode.STRUCTURE_RUN_NOT_REVIEWABLE)
    now = datetime.utcnow()
    if accept:
        await db.execute(
            update(SolutionRun)
            .where(
                SolutionRun.question_id == run.question_id,
                SolutionRun.solution_no == run.solution_no,
                SolutionRun.state == StructRunState.ACCEPTED.value,
                SolutionRun.id != run.id,
            )
            .values(state=StructRunState.SUPERSEDED.value, updated_at=now)
            .execution_options(synchronize_session=False)
        )
    run.state = StructRunState.ACCEPTED.value if accept else StructRunState.REJECTED.value
    run.reviewed_by = reviewer_id
    run.reviewed_at = now
    run.updated_at = now
    await db.flush()
    await recompute_question(db, run.question_id)
    return run


def thinking_load(method_type_ids: Sequence[Optional[int]], weights: Dict[int, float]) -> float:
    """各步骤权重之和:有方法类型的取类型权重,未归类的记 1。"""
    return round(sum(weights.get(t, 1.0) if t is not None else 1.0 for t in method_type_ids), 2)


async def recompute_question(db: AsyncSession, question_id: int) -> Optional[float]:
    """题目的思维量难度 = 已采纳解法的最小思维量;没有已采纳解答时为空。不提交。"""
    value = await db.scalar(
        select(func.min(SolutionRun.thinking_load)).where(
            SolutionRun.question_id == question_id, SolutionRun.state == StructRunState.ACCEPTED.value
        )
    )
    # 只改这一列;保留 updated_at,思维量变化不算题目被编辑。
    await db.execute(
        update(Question)
        .where(Question.id == question_id)
        .values(thinking_difficulty=value, updated_at=Question.updated_at)
        .execution_options(synchronize_session=False)
    )
    return value


async def recompute_for_method(db: AsyncSession, type_id: int) -> int:
    """方法类型权重变化:重算用到它的已采纳解答与题目。提交。返回重算的题数。"""
    runs = (
        await db.execute(
            select(SolutionRun)
            .options(selectinload(SolutionRun.steps))
            .where(
                SolutionRun.state == StructRunState.ACCEPTED.value,
                SolutionRun.id.in_(select(SolutionStep.run_id).where(SolutionStep.method_type_id == type_id)),
            )
        )
    ).scalars().all()
    question_ids = set()
    weights_by_subject: Dict[Optional[int], Dict[int, float]] = {}
    for run in runs:
        if run.subject_id not in weights_by_subject:
            weights_by_subject[run.subject_id] = await _method_weights(db, run.subject_id)
        run.thinking_load = thinking_load([s.method_type_id for s in run.steps], weights_by_subject[run.subject_id])
        question_ids.add(run.question_id)
    await db.flush()
    for question_id in question_ids:
        await recompute_question(db, question_id)
    await db.commit()
    return len(question_ids)

# endregion


# region 查询与序列化

async def get_run(db: AsyncSession, run_id: int) -> SolutionRun:
    run = await db.scalar(_run_query().where(SolutionRun.id == run_id))
    if run is None:
        raise NotFound("Solution not found", ErrorCode.STRUCTURE_SOLUTION_NOT_FOUND)
    return run


async def solution_view(db: AsyncSession, question: Question) -> Dict[str, Any]:
    """一道题的解答全貌:依据的题干拆解、各解法的已采纳 / 待审版本、进行中的任务、思维量难度。"""
    from . import service as struct_service

    stem = await struct_service.accepted_run(db, StructTargetType.QUESTION.value, question.id)
    runs = (
        await db.execute(
            _run_query()
            .where(
                SolutionRun.question_id == question.id,
                SolutionRun.state.in_([StructRunState.DRAFT.value, StructRunState.ACCEPTED.value]),
            )
            .order_by(SolutionRun.solution_no, SolutionRun.id)
        )
    ).scalars().all()
    paths = type_svc.path_names(await type_svc.list_types(db, question.subject_id)) if question.subject_id else {}
    weights = await _method_weights(db, question.subject_id)
    solutions: Dict[int, Dict[str, Any]] = {}
    for run in runs:
        entry = solutions.setdefault(run.solution_no, {"solution_no": run.solution_no, "accepted": None, "draft": None})
        key = "accepted" if run.state == StructRunState.ACCEPTED.value else "draft"
        entry[key] = serialize_run(run, question=question, stem_run_id=stem.id if stem else None, paths=paths, weights=weights)
    job = await active_job(db, question.id)
    return {
        "question_id": question.id,
        "subject_id": question.subject_id,
        "thinking_difficulty": question.thinking_difficulty,
        "stem": {
            "run_id": stem.id,
            "stale": (stem.source_revision or 1) != (question.content_revision or 1),
            "elements": [{"id": e.id, "ordinal": e.ordinal, "content": e.content} for e in stem.elements],
            "asks": [{"id": a.id, "ordinal": a.ordinal, "content": a.content} for a in stem.asks],
        } if stem else None,
        "solutions": [solutions[no] for no in sorted(solutions)],
        "job": {"id": job.id, "status": job.status, "paused_reason": job.paused_reason, "error": job.error} if job else None,
    }


def serialize_run(
    run: SolutionRun,
    *,
    question: Question,
    stem_run_id: Optional[int],
    paths: Dict[int, List[str]],
    weights: Dict[int, float],
) -> Dict[str, Any]:
    step_index = {step.id: step.ordinal for step in run.steps}
    return {
        "id": run.id,
        "question_id": run.question_id,
        "solution_no": run.solution_no,
        "stem_run_id": run.stem_run_id,
        # 题目内容改过、或依据的题干拆解已被取代:需要复核。
        "stale": (run.source_revision or 1) != (question.content_revision or 1) or run.stem_run_id != stem_run_id,
        "origin": run.origin,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "state": run.state,
        "thinking_load": run.thinking_load,
        "has_reference": bool(run.solution_text),
        "check_report": json.loads(run.check_report) if run.check_report else None,
        "check_errors": run.check_errors or 0,
        "check_warnings": run.check_warnings or 0,
        "created_at": run.created_at,
        "reviewed_at": run.reviewed_at,
        "steps": [
            {
                "id": step.id,
                "ordinal": step.ordinal,
                "goal": step.goal,
                "result": step.result,
                "method_type_id": step.method_type_id,
                "method_path": paths.get(step.method_type_id, []) if step.method_type_id else [],
                "method_hint": step.method_hint,
                "weight": weights.get(step.method_type_id, 1.0) if step.method_type_id else 1.0,
                "is_key": bool(step.is_key),
                "uses_elements": [l.element_id for l in step.links if l.role == "uses" and l.element_id],
                "uses_asks": [l.ask_id for l in step.links if l.role == "uses" and l.ask_id],
                "uses_steps": sorted(step_index[l.prev_step_id] for l in step.links if l.prev_step_id in step_index),
                "answers": [l.ask_id for l in step.links if l.role == "answers" and l.ask_id],
                "misconceptions": [{"description": m.description, "source": m.source} for m in step.misconceptions],
            }
            for step in run.steps
        ],
    }


async def active_job(db: AsyncSession, question_id: int) -> Optional[Job]:
    return await db.scalar(
        select(Job).where(
            Job.type == JOB_TYPE,
            Job.target_type == StructTargetType.QUESTION.value,
            Job.target_id == question_id,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        ).order_by(Job.id.desc()).limit(1)
    )


async def enqueue(
    db: AsyncSession, question: Question, *, solution_no: int, priority: int = JobPriority.USER,
    user_id: Optional[int], locale: Optional[str],
) -> Job:
    """排队拆解解答(同一道题已有未结束的任务时复用)。不提交。"""
    from app.services.jobs import job_service

    return await job_service.enqueue(
        db,
        type=JOB_TYPE,
        target_type=StructTargetType.QUESTION.value,
        target_id=question.id,
        priority=priority,
        payload={"solution_no": solution_no},
        user_id=user_id,
        subject_id=question.subject_id,
        locale=locale,
    )

# endregion


# region job 处理器

@register_handler
class SolutionJobHandler(JobHandler):
    """拆解一道题的解答。"""

    type = JOB_TYPE
    target_type = StructTargetType.QUESTION.value

    async def run(self, ctx: JobContext) -> None:
        from app.services.ai_resolver import resolve_provider_id

        from .decompose import ModelNotConfigured

        db = ctx.db
        if not await struct_settings.is_enabled(db):
            await ctx.fail("Question structure is disabled", error_code="structure_disabled")
            return
        question = await db.get(Question, ctx.target_id or 0)
        if question is None or question.deleted_at is not None:
            await ctx.fail("Question not found")
            return
        try:
            stem = await stem_context(db, question)
        except Invalid as exc:
            await ctx.fail(str(exc), error_code=ERROR_NEEDS_STEM)
            return
        provider_id = await resolve_provider_id(db, user_id=ctx.user_id, purpose="text")
        if provider_id is None:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        await ctx.set_progress(stage="decomposing")
        try:
            draft = await decompose_solution(db, question, stem, user_id=ctx.user_id)
        except ModelNotConfigured:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        except JobStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - 按 AI 错误类别暂停或失败
            logger.exception("Solution job %s failed", ctx.job_id)
            await ctx.handle_ai_error(exc, provider_id=provider_id)
            return
        await ctx.ai_succeeded(draft.provider_id or provider_id)
        await ctx.succeed(progress={"stage": "done", "errors": draft.report.error_count}, provider_id=provider_id)
        solution_no = int((ctx.payload or {}).get("solution_no") or 1)
        await save_draft(
            db, question, stem, draft, solution_no=solution_no, job_id=ctx.job_id, created_by=ctx.user_id
        )
        await db.commit()

# endregion


# region 内部实现

def _run_query():
    return select(SolutionRun).options(
        selectinload(SolutionRun.steps).selectinload(SolutionStep.links),
        selectinload(SolutionRun.steps).selectinload(SolutionStep.misconceptions),
    )


def _ref(ref: str) -> Tuple[str, int]:
    match = _REF_RE.match(ref)
    if not match:
        return "", 0
    return match.group(1).upper(), int(match.group(2))


def _issue(code: str, message: str, index: int, detail: str = "") -> Issue:
    return Issue(code=code, severity="error", message=message, target="step", index=index, detail=detail)


async def _method_weights(db: AsyncSession, subject_id: Optional[int]) -> Dict[int, float]:
    if subject_id is None:
        return {}
    rows = await db.execute(
        select(StructType.id, StructType.weight).where(
            StructType.subject_id == subject_id, StructType.kind == StructTypeKind.METHOD.value
        )
    )
    return {row[0]: float(row[1] or 1.0) for row in rows.all()}


async def _method_type_ids(db: AsyncSession, subject_id: Optional[int]) -> set:
    return set((await _method_weights(db, subject_id)).keys())

# endregion

