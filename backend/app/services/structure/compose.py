"""元素重组与命题(规格 §12.3 N2、N4):整组替换元素组、从多道题挑元素拼装新题。

两种任务共用一条流水线(``structure.compose`` 任务,``payload.mode`` 区分):

1. **写题**:AI 用给定的条件与设问写出一道通顺的题(``AI_STRUCT_COMPOSE_PROMPT``)。
   - ``compose``:条件 / 设问 / 元素组来自命题篮,可以跨题;
   - ``group``:原题的条件中,把一个元素组换成另一道题里同类型组合的元素组,其余条件与设问不变。
2. **结构一致性校验**:对新题拆解一次,检查输入的条件、设问都在,且没有多出未声明的条件
   (按规范化后的内容相似度匹配)。不一致时带着问题重写一次,仍不一致则任务失败。
3. **解题校验**:与变式相同(``variant.verify`` + 选择题兜底)。
4. **入库**:生成草稿题(查重照常),``group`` 记 ``variant_of``,``compose`` 对每道来源题记
   ``composed_from``;新题的拆解存为待审快照,供老师审核。

所有输入的条目都必须来自用户可见题目的**已采纳**拆解:替换进来的内容本身经过审核。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Invalid, NotFound
from app.core.api_errors import ErrorCode
from app.crud.crud_question import is_question_visible
from app.crud.crud_subject_prompt import subject_prompt as crud_subject_prompt
from app.models.import_task import ImportPauseReason
from app.models.job import Job, JobPriority
from app.models.question import Question
from app.models.question_relation import QuestionRelationType
from app.models.question_structure import (
    StructAsk,
    StructElement,
    StructElementGroup,
    StructOrigin,
    StructRun,
    StructRunState,
    StructTargetType,
)
from app.models.subject import Subject
from app.models.user import User
from app.services.jobs import JobContext, JobHandler, JobStopped, register_handler
from app.services.prompt_utils import apply_output_language, render_subject_prompt
from app.services.prompts import get_default_prompt
from app.services.question_dedup_core import normalize_text

from . import settings as struct_settings
from .text import build_stem_text

logger = logging.getLogger(__name__)

JOB_TYPE = "structure.compose"
PROMPT_KEY = "AI_STRUCT_COMPOSE_PROMPT"
# 规范化后的内容相似度达到它,就认为新题里的条目对应某条输入。
MATCH_RATIO = 0.6
RETRY_ON_INCONSISTENT = 1
ERROR_INCONSISTENT = "inconsistent"
ERROR_INVALID = "variant_invalid"


@dataclass
class ComposeSpec:
    """一次写题的输入:要用的条件、设问,来源题,以及「组替换」时的原题。"""

    mode: str
    subject_id: int
    q_type: str
    conditions: List[str]
    asks: List[str]
    source_question_ids: List[int]
    note: Optional[str] = None
    # group 模式:原题文本与被替换的条件(给 AI 参考写法)。
    original_text: Optional[str] = None
    replaced: List[str] = field(default_factory=list)


# region 输入校验(能力层与处理器共用)

async def load_items(
    db: AsyncSession, user: Any, *, element_ids: Sequence[int], ask_ids: Sequence[int], group_ids: Sequence[int]
) -> Tuple[List[StructElement], List[StructAsk], List[int], int]:
    """取命题篮里的条目,并校验:来自用户可见题目的已采纳拆解、同一学科。

    返回 (条件, 设问, 来源题 id, 学科 id)。元素组展开成它的条件。
    """
    group_rows = (
        await db.execute(
            select(StructElementGroup).options(selectinload(StructElementGroup.items)).where(StructElementGroup.id.in_(list(group_ids)))
        )
    ).scalars().all() if group_ids else []
    if len(group_rows) != len(set(group_ids)):
        raise NotFound("Group not found", ErrorCode.STRUCTURE_GROUP_NOT_FOUND)
    all_element_ids = list(dict.fromkeys([*element_ids, *(i.element_id for g in group_rows for i in g.items)]))
    elements = (await db.execute(select(StructElement).where(StructElement.id.in_(all_element_ids)))).scalars().all() if all_element_ids else []
    asks = (await db.execute(select(StructAsk).where(StructAsk.id.in_(list(ask_ids))))).scalars().all() if ask_ids else []
    if len(elements) != len(all_element_ids) or len(asks) != len(set(ask_ids)):
        raise NotFound("Structure item not found", ErrorCode.STRUCTURE_TARGET_NOT_FOUND)
    if not elements or not asks:
        raise Invalid("Pick at least one condition and one ask", ErrorCode.STRUCTURE_COMPOSE_INVALID)
    run_ids = {e.run_id for e in elements} | {a.run_id for a in asks}
    runs = (await db.execute(select(StructRun).where(StructRun.id.in_(run_ids)))).scalars().all()
    question_ids: List[int] = []
    subjects = set()
    for run in runs:
        if run.state != StructRunState.ACCEPTED.value or run.target_type != StructTargetType.QUESTION.value:
            raise Invalid("Only accepted question decompositions can be used", ErrorCode.STRUCTURE_COMPOSE_INVALID)
        question = await db.get(Question, run.target_id)
        if question is None or question.deleted_at is not None or not is_question_visible(question, user):
            raise NotFound("Question not found", ErrorCode.STRUCTURE_TARGET_NOT_FOUND)
        question_ids.append(question.id)
        subjects.add(question.subject_id)
    if len(subjects) != 1:
        raise Invalid("All items must come from the same subject", ErrorCode.STRUCTURE_COMPOSE_INVALID)
    order = {eid: i for i, eid in enumerate(all_element_ids)}
    return sorted(elements, key=lambda e: order[e.id]), list(asks), sorted(set(question_ids)), subjects.pop()


async def load_group_pair(db: AsyncSession, user: Any, group_id: int, source_group_id: int) -> Tuple[Question, StructRun, StructElementGroup, StructElementGroup, StructRun]:
    """组替换的两端:目标组所在题(须是已采纳、未过期的拆解)与来源组;条件类型组合必须一致。"""
    groups = {
        g.id: g for g in (
            await db.execute(
                select(StructElementGroup).options(selectinload(StructElementGroup.items))
                .where(StructElementGroup.id.in_([group_id, source_group_id]))
            )
        ).scalars().all()
    }
    if group_id not in groups or source_group_id not in groups or group_id == source_group_id:
        raise NotFound("Group not found", ErrorCode.STRUCTURE_GROUP_NOT_FOUND)
    target, source = groups[group_id], groups[source_group_id]
    target_run = await _accepted_run(db, target.run_id)
    source_run = await _accepted_run(db, source.run_id)
    question = await db.get(Question, target_run.target_id)
    source_question = await db.get(Question, source_run.target_id)
    for q in (question, source_question):
        if q is None or q.deleted_at is not None or not is_question_visible(q, user):
            raise NotFound("Question not found", ErrorCode.STRUCTURE_TARGET_NOT_FOUND)
    if question.subject_id != source_question.subject_id:
        raise Invalid("Groups must come from the same subject", ErrorCode.STRUCTURE_GROUP_MISMATCH)
    if (target_run.source_revision or 1) != (question.content_revision or 1):
        raise Invalid("The question changed after it was decomposed", ErrorCode.STRUCTURE_RUN_STALE)
    if not target.replaceable or group_types(target, target_run) != group_types(source, source_run):
        raise Invalid("The groups have different condition types", ErrorCode.STRUCTURE_GROUP_MISMATCH)
    return question, target_run, target, source, source_run


def group_types(group: StructElementGroup, run: StructRun) -> List[int]:
    """元素组成员的类型组合(排序后的类型 id 列表;有未归类成员时为空,不能参与替换匹配)。"""
    members = {i.element_id for i in group.items}
    types = [e.type_id for e in run.elements if e.id in members]
    return sorted(types) if types and all(types) else []


async def group_candidates(db: AsyncSession, group_id: int, viewer: Any, *, limit: int = 20) -> List[Dict[str, Any]]:
    """可替换进来的元素组:同学科其他题已采纳拆解中、条件类型组合相同的元素组(只列可见的题)。"""
    from app.crud.crud_question import visible_questions_filter

    group = await db.scalar(
        select(StructElementGroup).options(selectinload(StructElementGroup.items)).where(StructElementGroup.id == group_id)
    )
    if group is None:
        raise NotFound("Group not found", ErrorCode.STRUCTURE_GROUP_NOT_FOUND)
    run = await _accepted_run(db, group.run_id)
    wanted = group_types(group, run)
    if not wanted:
        return []
    visible = select(Question.id).where(Question.deleted_at.is_(None), visible_questions_filter(viewer))
    others = (
        await db.execute(
            select(StructRun)
            .options(
                selectinload(StructRun.elements),
                selectinload(StructRun.groups).selectinload(StructElementGroup.items),
            )
            .where(
                StructRun.subject_id == run.subject_id,
                StructRun.state == StructRunState.ACCEPTED.value,
                StructRun.target_type == StructTargetType.QUESTION.value,
                StructRun.target_id != run.target_id,
                StructRun.target_id.in_(visible),
                StructRun.id.in_(select(StructElementGroup.run_id)),
            )
        )
    ).scalars().all()
    out = []
    for other in others:
        for candidate in other.groups:
            if group_types(candidate, other) != wanted:
                continue
            members = {i.element_id for i in candidate.items}
            out.append({
                "group_id": candidate.id,
                "question_id": other.target_id,
                "name": candidate.name,
                "contents": [e.content for e in other.elements if e.id in members],
            })
            if len(out) >= limit:
                return out
    return out

# endregion


# region 写题与一致性校验

async def write_question(
    db: AsyncSession, spec: ComposeSpec, *, user_id: Optional[int], feedback: Sequence[str] = ()
) -> Dict[str, Any]:
    """让 AI 写题,返回 {"stem", "options", "analysis"}。"""
    from app.services.ai_errors import with_ai_retry
    from app.services.ai_provider import get_ai_provider
    from app.services.ai_resolver import resolve_model

    from .decompose import ModelNotConfigured

    resolved = await resolve_model(db, user_id=user_id, purpose="text")
    if resolved is None:
        raise ModelNotConfigured()
    provider = get_ai_provider(resolved.interface_type)
    subject = await db.get(Subject, spec.subject_id)
    override = await crud_subject_prompt.get_value(db, spec.subject_id, PROMPT_KEY)
    template = override if override is not None else get_default_prompt(PROMPT_KEY)
    system = (render_subject_prompt(template, subject) or "").replace("{question_type}", spec.q_type)
    system = apply_output_language(system, "extract")
    parts = []
    if spec.mode == "group" and spec.original_text:
        parts.append(
            "## Original question (rewrite it: replace the conditions listed under 'Replaced' by the new ones, "
            "keep everything else)\n<<<\n" + spec.original_text + "\n>>>"
        )
        parts.append("## Replaced conditions\n" + "\n".join(f"- {c}" for c in spec.replaced))
    parts.append("## Conditions\n" + "\n".join(f"C{i + 1}. {c}" for i, c in enumerate(spec.conditions)))
    parts.append("## Asks\n" + "\n".join(f"Q{i + 1}. {a}" for i, a in enumerate(spec.asks)))
    if spec.note:
        parts.append("## Teacher's note\n" + spec.note)
    if feedback:
        parts.append("## Problems in your previous question - fix them\n" + "\n".join(f"- {line}" for line in feedback))
    raw = await with_ai_retry(lambda: provider.generate_json(system, "\n\n".join(parts), resolved.config))
    if not isinstance(raw, dict) or not str(raw.get("stem") or "").strip():
        raise ValueError("Compose output has no stem")
    return raw


def to_content(written: Dict[str, Any], q_type: str) -> Tuple[Any, Optional[List[Dict[str, Any]]]]:
    """AI 写出的题 → (题干 RichDoc, 选项)。只有选择题保留选项。"""
    from app.services.question_content_converter import markdown_to_rich_doc

    content = markdown_to_rich_doc(str(written.get("stem") or "").strip())
    raw_options = written.get("options") if isinstance(written.get("options"), list) else []
    if q_type not in ("single_choice", "multiple_choice") or not raw_options:
        return content, None
    options = [
        {"label": chr(ord("A") + index), "content": markdown_to_rich_doc(str(text).strip())}
        for index, text in enumerate(raw_options)
        if str(text).strip()
    ]
    return content, options or None


def consistency_problems(
    expected_conditions: Sequence[str],
    expected_asks: Sequence[str],
    actual_conditions: Sequence[str],
    actual_asks: Sequence[str],
) -> List[str]:
    """新题的拆解与输入是否一致:输入都在、没有多出未声明的条件。返回问题清单(英文,给模型看)。"""
    problems: List[str] = []
    for label, expected, actual in (("condition", expected_conditions, actual_conditions), ("ask", expected_asks, actual_asks)):
        for item in expected:
            if not any(_similar(item, other) for other in actual):
                problems.append(f"the given {label} is missing or changed: {item}")
    for item in actual_conditions:
        if not any(_similar(item, other) for other in expected_conditions):
            problems.append(f"the question adds a condition that was not given: {item}")
    return problems

# endregion


# region 入队

async def enqueue(
    db: AsyncSession, *, payload: Dict[str, Any], subject_id: int, user_id: Optional[int], locale: Optional[str]
) -> Job:
    """排队一次写题任务(不与其他任务合并)。不提交。"""
    from app.services.jobs import job_service

    return await job_service.enqueue(
        db, type=JOB_TYPE, priority=JobPriority.USER, payload=payload,
        user_id=user_id, subject_id=subject_id, locale=locale,
    )

# endregion


# region job 处理器

@register_handler
class ComposeJobHandler(JobHandler):
    """拼装新题 / 整组替换生成变式。"""

    type = JOB_TYPE
    target_type = None

    async def run(self, ctx: JobContext) -> None:
        from app.services.ai_resolver import resolve_provider_id

        from .decompose import ModelNotConfigured

        db = ctx.db
        if not await struct_settings.is_enabled(db):
            await ctx.fail("Question structure is disabled", error_code="structure_disabled")
            return
        user = await db.scalar(
            select(User).options(selectinload(User.subject_memberships)).where(User.id == ctx.user_id)
        ) if ctx.user_id else None
        if user is None:
            await ctx.fail("User not found")
            return
        payload = ctx.payload or {}
        try:
            spec, source_question = await self._spec(db, user, payload)
        except (Invalid, NotFound) as exc:
            await ctx.fail(str(exc), error_code="invalid_input")
            return
        provider_id = await resolve_provider_id(db, user_id=ctx.user_id, purpose="text")
        if provider_id is None:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        try:
            result = await self._write_and_check(ctx, spec)
            if result is None:
                return
            written, content, options, draft = result
            await ctx.set_progress(stage="verifying")
            from .variant import guard_verdict, verify

            verdict = await verify(
                db, source_question if spec.mode == "group" else None, content, options,
                user_id=ctx.user_id, q_type=spec.q_type, subject_id=spec.subject_id,
            )
        except ModelNotConfigured:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        except JobStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - 按 AI 错误类别暂停或失败
            logger.exception("Compose job %s failed", ctx.job_id)
            await ctx.handle_ai_error(exc, provider_id=provider_id)
            return
        await ctx.ai_succeeded(provider_id)
        verdict = guard_verdict(verdict, spec.q_type, options)
        if not verdict.get("valid"):
            problems = [str(p) for p in verdict.get("problems") or []] or ["The new question is not valid"]
            await ctx.fail("; ".join(problems), error_code=ERROR_INVALID, problems=problems)
            return
        analysis = str(verdict.get("analysis") or written.get("analysis") or "").strip()
        created_id = await self._create(ctx, user, spec, content, options, analysis, draft)
        if created_id is None:
            return
        await ctx.succeed(progress={"stage": "done", "question_id": created_id, "mode": spec.mode}, provider_id=provider_id)
        await db.commit()

    # region 内部实现

    async def _spec(self, db: AsyncSession, user: User, payload: Dict[str, Any]) -> Tuple[ComposeSpec, Optional[Question]]:
        if payload.get("mode") == "group":
            question, run, target, source, source_run = await load_group_pair(
                db, user, int(payload["group_id"]), int(payload["source_group_id"])
            )
            replaced_ids = {i.element_id for i in target.items}
            incoming_ids = {i.element_id for i in source.items}
            kept = [e.content for e in run.elements if e.id not in replaced_ids]
            incoming = [e.content for e in source_run.elements if e.id in incoming_ids]
            return ComposeSpec(
                mode="group",
                subject_id=question.subject_id,
                q_type=getattr(question.q_type, "value", question.q_type),
                conditions=kept + incoming,
                asks=[a.content for a in run.asks],
                source_question_ids=[question.id],
                original_text=build_stem_text(question.content, question.options),
                replaced=[e.content for e in run.elements if e.id in replaced_ids],
            ), question
        elements, asks, question_ids, subject_id = await load_items(
            db, user,
            element_ids=payload.get("element_ids") or [],
            ask_ids=payload.get("ask_ids") or [],
            group_ids=payload.get("group_ids") or [],
        )
        return ComposeSpec(
            mode="compose",
            subject_id=subject_id,
            q_type=str(payload.get("q_type") or "free_response"),
            conditions=[e.content for e in elements],
            asks=[a.content for a in asks],
            source_question_ids=question_ids,
            note=payload.get("note") or None,
        ), None

    async def _write_and_check(self, ctx: JobContext, spec: ComposeSpec):
        """写题 → 拆解新题 → 一致性校验;不一致时带着问题重写一次,仍不一致则任务失败。"""
        from .decompose import decompose

        feedback: List[str] = []
        problems: List[str] = []
        for attempt in range(RETRY_ON_INCONSISTENT + 1):
            await ctx.set_progress(stage="writing", attempt=attempt + 1)
            written = await write_question(ctx.db, spec, user_id=ctx.user_id, feedback=feedback)
            content, options = to_content(written, spec.q_type)
            await ctx.set_progress(stage="checking", attempt=attempt + 1)
            draft = await decompose(
                ctx.db, stem_text=build_stem_text(content, options), subject_id=spec.subject_id, user_id=ctx.user_id
            )
            problems = consistency_problems(
                spec.conditions, spec.asks, [e.content for e in draft.elements], [a.content for a in draft.asks]
            )
            if not problems:
                return written, content, options, draft
            feedback = problems
        await ctx.fail("; ".join(problems[:5]), error_code=ERROR_INCONSISTENT, problems=problems[:10])
        return None

    async def _create(
        self, ctx: JobContext, user: User, spec: ComposeSpec, content: Any, options: Any, analysis: str, draft: Any
    ) -> Optional[int]:
        """生成草稿题,写来源关系,并把新题的拆解存为待审快照。"""
        from app import schemas
        from app.services.question_content_converter import markdown_to_rich_doc
        from app.services.question_relation_service import create_question_relation

        from . import service as struct_service
        from .variant import create_derived

        relation = QuestionRelationType.VARIANT_OF if spec.mode == "group" else QuestionRelationType.COMPOSED_FROM
        data = schemas.QuestionCreate(
            content=content,
            options=options,
            q_type=spec.q_type,
            subject_id=spec.subject_id,
            analysis=markdown_to_rich_doc(analysis) if analysis else None,
        )
        created_id = await create_derived(
            ctx, user, source_question_id=spec.source_question_ids[0], subject_id=spec.subject_id,
            data=data, relation_type=relation.value,
        )
        if created_id is None:
            return None
        for source_id in spec.source_question_ids[1:]:
            await create_question_relation(
                ctx.db, source_question_id=source_id, target_question_id=created_id, actor=user,
                commit=False, new_target=True, relation_type=relation.value,
            )
        target = await struct_service.load_target(ctx.db, StructTargetType.QUESTION.value, created_id)
        await struct_service.save_draft(
            ctx.db, target, draft, origin=StructOrigin.AI.value, job_id=ctx.job_id, created_by=user.id
        )
        await ctx.db.commit()
        return created_id

    # endregion

# endregion


# region 内部实现

def _similar(a: str, b: str) -> bool:
    left, right = normalize_text(a), normalize_text(b)
    if not left or not right:
        return False
    return left == right or SequenceMatcher(None, left, right).ratio() >= MATCH_RATIO


async def _accepted_run(db: AsyncSession, run_id: int) -> StructRun:
    run = await db.scalar(
        select(StructRun)
        .options(selectinload(StructRun.elements), selectinload(StructRun.asks))
        .where(StructRun.id == run_id)
    )
    if run is None or run.state != StructRunState.ACCEPTED.value or run.target_type != StructTargetType.QUESTION.value:
        raise Invalid("Only accepted question decompositions can be used", ErrorCode.STRUCTURE_GROUP_MISMATCH)
    return run

# endregion
