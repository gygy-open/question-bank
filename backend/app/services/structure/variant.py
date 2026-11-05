"""按参数槽生成变式题(规格 §12.3 N1):改值 → AI 重新解题校验 → 草稿题。

流程(``structure.variant`` 任务):

1. **取值**:老师填写的新值直接使用;选了「AI 取值」的参数,由 AI 在**已确认**的取值
   范围内取值,再按范围在本地复核(最小 / 最大、整数、枚举、排除值)。
2. **改写**:按参数在 ``stem_text`` 上的区间,从后往前改写题干 / 选项 RichDoc 的副本
   (``textmap.apply_replacements``),绝不做全文字符串替换。拆解之后题目又被改过时拒绝。
3. **校验**:AI 独立解答改写后的题目,判断条件是否自洽、答案是否唯一、数值是否合理、
   (选择题)干扰项是否仍然有效;原选项不再适用时,AI 按原有数量与风格重写选项
   (``new_options``),逐个替换选项内容。不成立时任务失败并给出原因,不生成题。
4. **入库**:经 ``question.derived.create`` 生成草稿题(查重照常进行),关系类型
   ``variant_of``;解析写入新题;按学科开关自动排队拆解。

能力层负责入队前的同步校验(权限、参数、范围是否确认、区间能否映射),处理器在执行前
重新校验一次(排队期间题目可能被改)。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Conflict, Invalid, NotFound
from app.core.api_errors import ErrorCode
from app.crud.crud_subject_prompt import subject_prompt as crud_subject_prompt
from app.models.import_task import ImportPauseReason
from app.models.job import ACTIVE_JOB_STATUSES, Job, JobPriority
from app.models.question import Question
from app.models.question_relation import QuestionRelationType
from app.models.question_structure import StructParam, StructRun, StructRunState, StructTargetType
from app.models.subject import Subject
from app.models.user import User
from app.services.jobs import JobContext, JobHandler, JobStopped, register_handler
from app.services.prompt_utils import apply_output_language, render_subject_prompt
from app.services.prompts import get_default_prompt

from . import settings as struct_settings
from .text import build_stem_text
from .textmap import Replacement, UnmappableSpan, apply_replacements

logger = logging.getLogger(__name__)

JOB_TYPE = "structure.variant"
PROMPT_KEY = "AI_STRUCT_VARIANT_PROMPT"
ERROR_INVALID_VARIANT = "variant_invalid"
ERROR_STALE = "structure_stale"
ERROR_DUPLICATE = "duplicate"
ERROR_OUT_OF_DOMAIN = "out_of_domain"

_CHOOSE_PROMPT = """You choose new values for the parameters of a question so that a teacher gets a valid variant.
For each parameter you get its current value and the allowed domain. Pick a value that differs from the current one,
stays inside the domain and keeps the question solvable with a clean answer. Write values exactly as they should
appear in the question (LaTeX without `$` when the current value is LaTeX).
Return only one JSON object: {"values": {"<parameter id>": "<new value>"}}"""


@dataclass
class VariantPlan:
    """一次变式请求校验通过后的内容。"""

    question: Question
    run: StructRun
    params: Dict[int, StructParam]
    values: Dict[int, str]
    auto: List[int]


# region 校验与入队

async def plan_variant(
    db: AsyncSession,
    question: Question,
    *,
    run_id: Optional[int],
    values: Dict[int, str],
    auto: Sequence[int],
) -> VariantPlan:
    """校验一次变式请求(不写库)。``run_id`` 缺省时用题目当前采纳的拆解。"""
    query = select(StructRun).options(selectinload(StructRun.params))
    if run_id is not None:
        run = await db.scalar(query.where(StructRun.id == run_id))
    else:
        run = await db.scalar(
            query.where(
                StructRun.target_type == StructTargetType.QUESTION.value,
                StructRun.target_id == question.id,
                StructRun.state == StructRunState.ACCEPTED.value,
            ).order_by(StructRun.id.desc()).limit(1)
        )
    if run is None or run.target_type != StructTargetType.QUESTION.value or run.target_id != question.id:
        raise NotFound("Structure run not found", ErrorCode.STRUCTURE_RUN_NOT_FOUND)
    if run.state == StructRunState.REJECTED.value:
        raise Invalid("Rejected structures cannot be used", ErrorCode.STRUCTURE_RUN_NOT_REVIEWABLE)
    if (run.source_revision or 1) != (question.content_revision or 1):
        raise Invalid("The question changed after it was decomposed", ErrorCode.STRUCTURE_RUN_STALE)

    params = {p.id: p for p in run.params}
    cleaned: Dict[int, str] = {}
    for param_id, value in values.items():
        param = params.get(int(param_id))
        if param is None or not param.replaceable:
            raise Invalid("Unknown parameter", ErrorCode.STRUCTURE_PARAM_NOT_FOUND, {"param_id": param_id})
        text = _clean_value(str(value), param.value)
        if text and text != param.value:
            cleaned[param.id] = text
    auto_ids: List[int] = []
    for param_id in dict.fromkeys(auto):
        param = params.get(int(param_id))
        if param is None or not param.replaceable:
            raise Invalid("Unknown parameter", ErrorCode.STRUCTURE_PARAM_NOT_FOUND, {"param_id": param_id})
        if param.id in cleaned:
            continue
        if not param.domain or not param.domain_confirmed:
            raise Invalid(
                "Parameter domain is not confirmed", ErrorCode.STRUCTURE_PARAM_DOMAIN_UNCONFIRMED,
                {"name": param.name},
            )
        auto_ids.append(param.id)
    if not cleaned and not auto_ids:
        raise Invalid("No parameter is changed", ErrorCode.STRUCTURE_VARIANT_EMPTY)

    # 先用原值演练一次映射:区间落在定界符 / 标签上、或跨节点时,入队前就拒绝。
    trial = [Replacement(p.span_start, p.span_end, cleaned.get(p.id, p.value)) for p in _changed(params, cleaned, auto_ids)]
    try:
        apply_replacements(question.content, question.options, run.stem_text, trial)
    except UnmappableSpan as exc:
        raise Invalid(str(exc), ErrorCode.STRUCTURE_PARAM_UNMAPPABLE)
    return VariantPlan(question=question, run=run, params=params, values=cleaned, auto=auto_ids)


async def active_job(db: AsyncSession, question_id: int) -> Optional[Job]:
    return await db.scalar(
        select(Job).where(
            Job.type == JOB_TYPE,
            Job.target_type == StructTargetType.QUESTION.value,
            Job.target_id == question_id,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        ).order_by(Job.id.desc()).limit(1)
    )


async def last_job(db: AsyncSession, question_id: int) -> Optional[Job]:
    return await db.scalar(
        select(Job).where(
            Job.type == JOB_TYPE,
            Job.target_type == StructTargetType.QUESTION.value,
            Job.target_id == question_id,
        ).order_by(Job.id.desc()).limit(1)
    )


async def enqueue(
    db: AsyncSession, plan: VariantPlan, *, user_id: Optional[int], locale: Optional[str]
) -> Job:
    """排队生成变式(一道题同时只能有一个变式任务)。不提交。"""
    from app.services.jobs import job_service

    if await active_job(db, plan.question.id) is not None:
        raise Conflict("A variant is already being generated", ErrorCode.STRUCTURE_VARIANT_RUNNING)
    return await job_service.enqueue(
        db,
        type=JOB_TYPE,
        target_type=StructTargetType.QUESTION.value,
        target_id=plan.question.id,
        priority=JobPriority.USER,
        payload={"run_id": plan.run.id, "values": {str(k): v for k, v in plan.values.items()}, "auto": plan.auto},
        user_id=user_id,
        subject_id=plan.question.subject_id,
        locale=locale,
    )


def check_domain(value: str, domain: Optional[Dict[str, Any]]) -> bool:
    """AI 取的值是否在取值范围内(只检查能检查的部分)。"""
    if not domain:
        return True
    if domain.get("values") and value not in domain["values"]:
        return False
    if value in (domain.get("exclude") or []):
        return False
    number = _number(value)
    if any(key in domain for key in ("min", "max", "integer")):
        if number is None:
            return False
        if "min" in domain and number < domain["min"]:
            return False
        if "max" in domain and number > domain["max"]:
            return False
        if domain.get("integer") and abs(number - round(number)) > 1e-9:
            return False
    return True

# endregion


# region job 处理器

@register_handler
class VariantJobHandler(JobHandler):
    """生成一道变式题。"""

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
        user = await db.scalar(
            select(User).options(selectinload(User.subject_memberships)).where(User.id == ctx.user_id)
        ) if ctx.user_id else None
        if question is None or question.deleted_at is not None or user is None:
            await ctx.fail("Question not found")
            return
        payload = ctx.payload or {}
        try:
            plan = await plan_variant(
                db, question,
                run_id=payload.get("run_id"),
                values={int(k): v for k, v in (payload.get("values") or {}).items()},
                auto=payload.get("auto") or [],
            )
        except (Invalid, NotFound) as exc:
            await ctx.fail(str(exc), error_code=ERROR_STALE)
            return

        provider_id = await resolve_provider_id(db, user_id=ctx.user_id, purpose="text")
        if provider_id is None:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        try:
            values = dict(plan.values)
            if plan.auto:
                await ctx.set_progress(stage="choosing")
                values.update(await choose_values(db, plan, user_id=ctx.user_id))
            content, options = apply_replacements(
                question.content, question.options, plan.run.stem_text,
                [Replacement(p.span_start, p.span_end, values[p.id]) for p in plan.params.values() if p.id in values],
            )
            await ctx.set_progress(stage="verifying")
            verdict = await verify(db, question, content, options, user_id=ctx.user_id)
        except ModelNotConfigured:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        except _OutOfDomain as exc:
            await ctx.fail(str(exc), error_code=ERROR_OUT_OF_DOMAIN)
            return
        except UnmappableSpan as exc:
            await ctx.fail(str(exc), error_code=ERROR_STALE)
            return
        except JobStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - 按 AI 错误类别暂停或失败
            logger.exception("Variant job %s failed", ctx.job_id)
            await ctx.handle_ai_error(exc, provider_id=provider_id)
            return
        await ctx.ai_succeeded(provider_id)

        changes = {plan.params[pid].name: [plan.params[pid].value, v] for pid, v in values.items()}
        options, options_rewritten = replace_options(options, verdict.get("new_options"))
        if verdict.get("new_options") and not options_rewritten and verdict.get("valid"):
            verdict = {**verdict, "valid": False, "problems": ["The rewritten options do not match the original options"]}
        verdict = guard_verdict(verdict, question.q_type, options)
        if not verdict.get("valid"):
            problems = [str(p) for p in verdict.get("problems") or []] or ["The variant is not a valid question"]
            await ctx.fail("; ".join(problems), error_code=ERROR_INVALID_VARIANT, changes=changes, problems=problems)
            return

        created_id = await self._create(ctx, user, question, content, options, verdict)
        if created_id is None:
            return
        await ctx.succeed(
            progress={
                "stage": "done", "question_id": created_id, "changes": changes, "options_rewritten": options_rewritten,
            },
            provider_id=provider_id,
        )
        await db.commit()

    async def _create(
        self, ctx: JobContext, user: User, source: Question, content: Any, options: Any, verdict: Dict[str, Any]
    ) -> Optional[int]:
        """经能力层生成草稿题(查重、关系、自动拆解都在里面)。重复时任务失败。"""
        from app import schemas
        from app.services.question_content_converter import markdown_to_rich_doc

        linked = await _with_links(ctx.db, source)
        kp_ids = [kp.id for kp in linked.knowledge_points]
        tag_ids = [tag.id for tag in linked.tags]
        analysis = str(verdict.get("analysis") or "").strip()
        data = schemas.QuestionCreate(
            content=content,
            options=options,
            q_type=source.q_type,
            difficulty=source.difficulty or 1,
            visibility=source.visibility,
            source=source.source,
            subject_id=source.subject_id,
            knowledge_point_ids=kp_ids,
            tag_ids=tag_ids,
            analysis=markdown_to_rich_doc(analysis) if analysis else None,
        )
        return await create_derived(
            ctx, user, source_question_id=source.id, subject_id=source.subject_id, data=data,
            relation_type=QuestionRelationType.VARIANT_OF.value,
        )

# endregion


async def create_derived(
    ctx: JobContext, user: User, *, source_question_id: int, subject_id: Optional[int], data: Any, relation_type: str
) -> Optional[int]:
    """经能力层生成派生草稿题(查重、关系、自动拆解都在里面),返回新题 id;失败时任务失败并返回 None。

    派生题本来就与原题「高度相似」:只有完全相同的题(例如之前生成过同样的题)才拦下。
    """
    from app import capabilities
    from app.capabilities.context import ExecutionContext, Surface
    from app.capabilities.errors import DomainError, DuplicateSuspected
    from app.capabilities.questions import DerivedQuestionCreateInput

    exec_ctx = ExecutionContext(db=ctx.db, actor=user, surface=Surface.WORKER, subject_id=subject_id)
    for attempt in range(2):
        try:
            created = await capabilities.run(
                "question.derived.create",
                exec_ctx,
                DerivedQuestionCreateInput(source_question_id=source_question_id, data=data, relation_type=relation_type),
            )
            return created.id
        except DuplicateSuspected as exc:
            candidates = (exc.params or {}).get("candidates") or []
            if attempt == 0 and candidates and all(c.get("level") != "duplicate" for c in candidates):
                data.allow_duplicate = True
                continue
            await ctx.fail(
                "The question duplicates an existing one", error_code=ERROR_DUPLICATE,
                duplicates=[c.get("id") for c in candidates],
            )
            return None
        except DomainError as exc:
            await ctx.fail(str(exc) or "Failed to save the question", error_code="save_failed")
            return None
    return None


# region 调用 AI

class _OutOfDomain(Exception):
    """AI 取的值不在取值范围内。"""


async def choose_values(db: AsyncSession, plan: VariantPlan, *, user_id: Optional[int]) -> Dict[int, str]:
    """让 AI 为「AI 取值」的参数在已确认的范围内取值,并在本地复核范围。"""
    from app.services.ai_errors import with_ai_retry
    from app.services.ai_provider import get_ai_provider
    from app.services.ai_resolver import resolve_model

    from .decompose import ModelNotConfigured

    resolved = await resolve_model(db, user_id=user_id, purpose="text")
    if resolved is None:
        raise ModelNotConfigured()
    provider = get_ai_provider(resolved.interface_type)
    lines = []
    for param_id in plan.auto:
        param = plan.params[param_id]
        lines.append(f"- id {param.id}: {param.name} = {param.value}; domain {param.domain}")
    fixed = [f"- {plan.params[pid].name}: {plan.params[pid].value} -> {value}" for pid, value in plan.values.items()]
    user = "## Question\n<<<\n" + plan.run.stem_text + "\n>>>\n\n## Parameters to choose\n" + "\n".join(lines)
    if fixed:
        user += "\n\n## Already changed by the teacher\n" + "\n".join(fixed)
    raw = await with_ai_retry(lambda: provider.generate_json(_CHOOSE_PROMPT, user, resolved.config))
    chosen = (raw or {}).get("values") if isinstance(raw, dict) else None
    if not isinstance(chosen, dict):
        raise ValueError("Variant value output is not a JSON object")
    out: Dict[int, str] = {}
    for param_id in plan.auto:
        param = plan.params[param_id]
        value = _clean_value(str(chosen.get(str(param_id), "")), param.value)
        domain = json.loads(param.domain) if param.domain else None
        if not value or value == param.value or not check_domain(value, domain):
            raise _OutOfDomain(f"AI chose an invalid value for {param.name}: {value or '(empty)'}")
        out[param_id] = value
    return out


async def verify(
    db: AsyncSession,
    source: Optional[Question],
    content: Any,
    options: Any,
    *,
    user_id: Optional[int],
    q_type: Any = None,
    subject_id: Optional[int] = None,
) -> Dict[str, Any]:
    """让 AI 独立解答改写后(或新拼装)的题目并判断是否成立。``source`` 为空表示没有原题。"""
    from app.services.ai_errors import with_ai_retry
    from app.services.ai_provider import get_ai_provider
    from app.services.ai_resolver import resolve_model

    from .decompose import ModelNotConfigured

    resolved = await resolve_model(db, user_id=user_id, purpose="text")
    if resolved is None:
        raise ModelNotConfigured()
    provider = get_ai_provider(resolved.interface_type)
    subject_id = source.subject_id if source is not None else subject_id
    q_type = getattr(source.q_type if source is not None else q_type, "value", source.q_type if source is not None else q_type)
    subject = await db.get(Subject, subject_id) if subject_id else None
    override = await crud_subject_prompt.get_value(db, subject_id, PROMPT_KEY) if subject_id else None
    template = override if override is not None else get_default_prompt(PROMPT_KEY)
    system = apply_output_language(render_subject_prompt(template, subject) or "", "extract")
    original = build_stem_text(source.content, source.options) if source is not None else "(none - this is a newly composed question)"
    user = (
        f"## Question type\n{q_type}\n\n## Original question\n<<<\n"
        + original
        + "\n>>>\n\n## Variant\n<<<\n"
        + build_stem_text(content, options)
        + "\n>>>"
    )
    raw = await with_ai_retry(lambda: provider.generate_json(system, user, resolved.config))
    if not isinstance(raw, dict):
        raise ValueError("Variant verification output is not a JSON object")
    return raw

# endregion


# region 内部实现

CHOICE_TYPES = ("single_choice", "multiple_choice")


def guard_verdict(verdict: Dict[str, Any], q_type: Any, options: Any) -> Dict[str, Any]:
    """在 AI 的结论上做本地兜底:选择题必须指出正确选项,且正确选项的标签必须存在。"""
    if not verdict.get("valid"):
        return verdict
    q_type = getattr(q_type, "value", q_type)
    if q_type not in CHOICE_TYPES or not isinstance(options, list):
        return verdict
    labels = {
        str(option.get("label") or chr(ord("A") + index)) if isinstance(option, dict) else chr(ord("A") + index)
        for index, option in enumerate(options)
    }
    correct = [str(label).strip().rstrip(".．") for label in verdict.get("correct_options") or []]
    problem = None
    if not correct:
        problem = "No option is correct for the variant"
    elif any(label not in labels for label in correct):
        problem = "The correct option does not exist"
    elif q_type == "single_choice" and len(correct) != 1:
        problem = "A single-choice variant must have exactly one correct option"
    if problem is None:
        return verdict
    return {**verdict, "valid": False, "problems": [*(verdict.get("problems") or []), problem]}


def replace_options(options: Any, new_options: Any) -> tuple[Any, bool]:
    """校验时 AI 重写了选项(数量必须一致):逐个替换选项内容,标签不变。返回 (选项, 是否替换)。"""
    from app.services.question_content_converter import markdown_to_rich_doc

    if not isinstance(options, list) or not isinstance(new_options, list) or len(new_options) != len(options):
        return options, False
    texts = [str(item).strip() for item in new_options]
    if not all(texts):
        return options, False
    out = []
    for option, text in zip(options, texts):
        if isinstance(option, dict):
            out.append({**option, "content": markdown_to_rich_doc(text)})
        else:
            out.append(text)
    return out, True


def _changed(params: Dict[int, StructParam], values: Dict[int, str], auto: Sequence[int]) -> List[StructParam]:
    return [p for p in params.values() if p.id in values or p.id in auto]


def _clean_value(value: str, original: str) -> str:
    """新值去掉首尾空白;原值不带 ``$`` 时(公式内的参数),新值外层的 ``$`` 一并去掉。"""
    value = value.strip()
    if "$" not in original and len(value) >= 2 and value.startswith("$") and value.endswith("$"):
        value = value[1:-1].strip()
    return value


_FRAC_RE = re.compile(r"^(-?)\\[dt]?frac\{(-?\d+(?:\.\d+)?)\}\{(-?\d+(?:\.\d+)?)\}$")


def _number(value: str) -> Optional[float]:
    text = value.replace(" ", "")
    try:
        return float(text)
    except ValueError:
        pass
    match = _FRAC_RE.match(text)
    if match and float(match.group(3)) != 0:
        sign = -1 if match.group(1) else 1
        return sign * float(match.group(2)) / float(match.group(3))
    return None


async def _with_links(db: AsyncSession, question: Question) -> Question:
    """带出知识点与标签(复制到变式题)。"""
    return await db.scalar(
        select(Question)
        .options(selectinload(Question.knowledge_points), selectinload(Question.tags))
        .where(Question.id == question.id)
        .execution_options(populate_existing=True)
    )

# endregion
