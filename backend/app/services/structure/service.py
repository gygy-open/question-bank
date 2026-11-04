"""题干结构化的业务服务:拆解对象、拆解快照的保存 / 审核、入队、序列化、同结构题、检索条件。

能力层(``app/capabilities/structure.py``)、job 处理器(``job.py``)与题目检索共用本模块。
除非函数说明写了「会提交」,本模块只写入不提交。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Invalid, NotFound
from app.core.api_errors import ErrorCode
from app.models.job import Job, JobPriority, JobStatus, ACTIVE_JOB_STATUSES
from app.models.question import Question
from app.models.question_structure import (
    StructAsk,
    StructAskElement,
    StructElement,
    StructElementGroup,
    StructElementGroupItem,
    StructOrigin,
    StructParam,
    StructRun,
    StructRunState,
    StructTargetType,
    StructType,
    StructTypeKind,
)
from app.models.stimulus import Stimulus

from . import settings as struct_settings
from . import types as type_svc
from .decompose import Draft, DraftAsk, DraftElement, SharedCondition, run_check
from .text import build_stem_text, stimulus_text

JOB_TYPE = "structure.decompose"


@dataclass
class Target:
    """一个可拆解的对象(题目或材料)当前的状态。"""

    type: str
    id: int
    subject_id: Optional[int]
    revision: int
    stem_text: str
    # 题目所属材料;材料本身为 None。
    stimulus_id: Optional[int]
    # 题目 / 材料 ORM 对象,供可见性判断。
    obj: Any


# region 拆解对象

async def load_target(db: AsyncSession, target_type: str, target_id: int) -> Target:
    """取题目或材料(未删除),并生成当前的题干快照。不存在抛 NotFound。"""
    if target_type == StructTargetType.QUESTION.value:
        question = await db.get(Question, target_id)
        if question is None or question.deleted_at is not None:
            raise NotFound("Question not found", ErrorCode.STRUCTURE_TARGET_NOT_FOUND)
        return Target(
            type=target_type,
            id=question.id,
            subject_id=question.subject_id,
            revision=question.content_revision or 1,
            stem_text=build_stem_text(question.content, question.options),
            stimulus_id=question.stimulus_id,
            obj=question,
        )
    if target_type == StructTargetType.STIMULUS.value:
        stimulus = await db.get(Stimulus, target_id)
        if stimulus is None or stimulus.deleted_at is not None:
            raise NotFound("Material not found", ErrorCode.STRUCTURE_TARGET_NOT_FOUND)
        return Target(
            type=target_type,
            id=stimulus.id,
            subject_id=stimulus.subject_id,
            revision=stimulus.content_revision or 1,
            stem_text=stimulus_text(stimulus.content) or "",
            stimulus_id=None,
            obj=stimulus,
        )
    raise Invalid("Unknown structure target", ErrorCode.STRUCTURE_INVALID_ITEM)


async def current_revisions(db: AsyncSession, target_type: str, ids: Iterable[int]) -> Dict[int, int]:
    """一批对象当前的 content_revision(判断拆解是否过期)。"""
    ids = list(set(ids))
    if not ids:
        return {}
    model = Question if target_type == StructTargetType.QUESTION.value else Stimulus
    rows = await db.execute(select(model.id, model.content_revision).where(model.id.in_(ids)))
    return {row[0]: row[1] or 1 for row in rows.all()}

# endregion


# region 拆解快照:查询

async def get_run(db: AsyncSession, run_id: int) -> StructRun:
    """按 id 取拆解(含条件、设问及依赖),不存在抛 NotFound。"""
    run = await db.scalar(_run_query().where(StructRun.id == run_id))
    if run is None:
        raise NotFound("Structure run not found", ErrorCode.STRUCTURE_RUN_NOT_FOUND)
    return run


async def accepted_run(db: AsyncSession, target_type: str, target_id: int) -> Optional[StructRun]:
    """对象当前采纳的拆解。"""
    return await db.scalar(
        _run_query()
        .where(
            StructRun.target_type == target_type,
            StructRun.target_id == target_id,
            StructRun.state == StructRunState.ACCEPTED.value,
        )
        .order_by(StructRun.id.desc())
        .limit(1)
    )


async def pending_draft(db: AsyncSession, target_type: str, target_id: int) -> Optional[StructRun]:
    """对象最新的待审拆解(保存新草稿时旧草稿会被取代,所以最多一条)。"""
    return await db.scalar(
        _run_query()
        .where(
            StructRun.target_type == target_type,
            StructRun.target_id == target_id,
            StructRun.state == StructRunState.DRAFT.value,
        )
        .order_by(StructRun.id.desc())
        .limit(1)
    )


async def shared_conditions(db: AsyncSession, stimulus_id: int) -> List[SharedCondition]:
    """材料可被小题引用的条件:优先取已采纳的拆解,其次取待审的。"""
    run = await accepted_run(db, StructTargetType.STIMULUS.value, stimulus_id)
    if run is None:
        run = await pending_draft(db, StructTargetType.STIMULUS.value, stimulus_id)
    if run is None:
        return []
    return [SharedCondition(element_id=e.id, content=e.content) for e in run.elements if e.ref_element_id is None]


def is_stale(run: StructRun, current_revision: Optional[int]) -> bool:
    """拆解之后对象内容又改过。"""
    return current_revision is not None and (run.source_revision or 1) != current_revision


async def active_job(db: AsyncSession, target_type: str, target_id: int) -> Optional[Job]:
    """对象未结束的拆解 job(排队 / 执行中 / 暂停)。"""
    return await db.scalar(
        select(Job)
        .where(
            Job.type == JOB_TYPE,
            Job.target_type == target_type,
            Job.target_id == target_id,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(Job.id.desc())
        .limit(1)
    )

# endregion


# region 拆解快照:保存与审核

async def save_draft(
    db: AsyncSession,
    target: Target,
    draft: Draft,
    *,
    origin: str = StructOrigin.AI.value,
    job_id: Optional[int] = None,
    created_by: Optional[int] = None,
) -> StructRun:
    """把一次拆解保存为待审快照(flush,不提交)。同一对象此前的待审快照被取代。"""
    await db.execute(
        update(StructRun)
        .where(
            StructRun.target_type == target.type,
            StructRun.target_id == target.id,
            StructRun.state == StructRunState.DRAFT.value,
        )
        .values(state=StructRunState.SUPERSEDED.value, updated_at=datetime.utcnow())
        .execution_options(synchronize_session=False)
    )
    run = StructRun(
        target_type=target.type,
        target_id=target.id,
        subject_id=target.subject_id,
        source_revision=target.revision,
        stem_text=target.stem_text,
        origin=origin,
        model=draft.model,
        prompt_version=draft.prompt_version,
        job_id=job_id,
        state=StructRunState.DRAFT.value,
        check_report=json.dumps(draft.report.to_dict(), ensure_ascii=False),
        check_errors=draft.report.error_count,
        check_warnings=draft.report.warning_count,
        created_by=created_by,
    )
    db.add(run)
    await db.flush()
    elements: List[StructElement] = []
    for ordinal, item in enumerate(draft.elements):
        element = StructElement(
            run_id=run.id,
            ordinal=ordinal,
            content=item.content,
            type_id=item.type_id,
            type_hint=item.type_hint,
            facet=item.facet,
            span_start=item.span[0] if item.span else None,
            span_end=item.span[1] if item.span else None,
            ref_element_id=item.ref_element_id,
        )
        db.add(element)
        elements.append(element)
    await db.flush()
    for ordinal, item in enumerate(draft.asks):
        ask = StructAsk(
            run_id=run.id,
            ordinal=ordinal,
            content=item.content,
            type_id=item.type_id,
            type_hint=item.type_hint,
            span_start=item.span[0] if item.span else None,
            span_end=item.span[1] if item.span else None,
        )
        db.add(ask)
        await db.flush()
        for index in sorted(set(item.depends_on)):
            if 0 <= index < len(elements):
                db.add(StructAskElement(ask_id=ask.id, element_id=elements[index].id))
    await db.flush()
    return run


async def save_human(
    db: AsyncSession,
    target: Target,
    *,
    elements: Sequence[Dict[str, Any]],
    asks: Sequence[Dict[str, Any]],
    user_id: Optional[int],
    base_run: Optional[StructRun] = None,
) -> StructRun:
    """保存人工修改:基于当前题干快照新建一条 human 快照(不覆盖 AI 的结果,便于对比)。

    ``elements`` / ``asks`` 的每项:content(必填)、source、span_start/span_end、type_id、
    type_hint、facet(仅条件)、ref_element_id(仅条件)、depends_on(仅设问,条件下标)。
    基于的旧快照与当前内容版本一致时沿用它的原文快照,否则用当前题干重新生成。
    """
    if base_run is not None and base_run.source_revision == target.revision:
        target = Target(**{**target.__dict__, "stem_text": base_run.stem_text})
    allowed = await _allowed_type_ids(db, target.subject_id)
    draft_elements = [
        DraftElement(
            content=_required_text(item.get("content")),
            source=item.get("source") or None,
            type_id=_checked_type(item.get("type_id"), allowed, StructTypeKind.CONDITION),
            type_hint=(item.get("type_hint") or None),
            facet=item.get("facet") or None,
            span=_span(item, target.stem_text),
            ref_element_id=item.get("ref_element_id") or None,
        )
        for item in elements
    ]
    draft_asks = [
        DraftAsk(
            content=_required_text(item.get("content")),
            source=item.get("source") or None,
            type_id=_checked_type(item.get("type_id"), allowed, StructTypeKind.ASK),
            type_hint=(item.get("type_hint") or None),
            span=_span(item, target.stem_text),
            depends_on=[int(i) for i in item.get("depends_on") or [] if isinstance(i, int) or str(i).isdigit()],
        )
        for item in asks
    ]
    shared = await shared_conditions(db, target.stimulus_id) if target.stimulus_id else []
    report = run_check(target.stem_text, draft_elements, draft_asks, shared)
    draft = Draft(elements=draft_elements, asks=draft_asks, report=report)
    return await save_draft(db, target, draft, origin=StructOrigin.HUMAN.value, created_by=user_id)


async def review(db: AsyncSession, run: StructRun, *, accept: bool, reviewer_id: Optional[int]) -> StructRun:
    """采纳或驳回一条待审快照(flush,不提交)。采纳时同一对象原先采纳的快照被取代。"""
    if run.state != StructRunState.DRAFT.value:
        raise Invalid("Only draft structures can be reviewed", ErrorCode.STRUCTURE_RUN_NOT_REVIEWABLE)
    now = datetime.utcnow()
    if accept:
        await db.execute(
            update(StructRun)
            .where(
                StructRun.target_type == run.target_type,
                StructRun.target_id == run.target_id,
                StructRun.state == StructRunState.ACCEPTED.value,
                StructRun.id != run.id,
            )
            .values(state=StructRunState.SUPERSEDED.value, updated_at=now)
            .execution_options(synchronize_session=False)
        )
    run.state = StructRunState.ACCEPTED.value if accept else StructRunState.REJECTED.value
    run.reviewed_by = reviewer_id
    run.reviewed_at = now
    run.updated_at = now
    await db.flush()
    return run

# endregion


# region 入队

async def enqueue_decompose(
    db: AsyncSession,
    target_type: str,
    target_id: int,
    *,
    priority: int = JobPriority.USER,
    user_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    locale: Optional[str] = None,
) -> Job:
    """为一个对象排队拆解(已有未结束的 job 时复用它,优先级取较高者)。不提交。"""
    from app.services.jobs import job_service

    return await job_service.enqueue(
        db,
        type=JOB_TYPE,
        target_type=target_type,
        target_id=target_id,
        priority=priority,
        user_id=user_id,
        subject_id=subject_id,
        locale=locale,
    )


async def auto_enqueue_questions(
    db: AsyncSession, questions: Sequence[Question], *, user_id: Optional[int]
) -> int:
    """题目入库后:结构化开启、且所属学科开启了「入库自动拆解」时排队拆解。不提交。返回入队数。

    已有待审拆解、或已采纳且未过期的题跳过(例如审核通过的题之前已经拆过)。
    """
    if not questions or not await struct_settings.is_enabled(db):
        return 0
    enabled_by_subject: Dict[int, bool] = {}
    candidates: List[Question] = []
    for question in questions:
        subject_id = question.subject_id
        if subject_id is None:
            continue
        if subject_id not in enabled_by_subject:
            enabled_by_subject[subject_id] = await struct_settings.is_auto_decompose(db, subject_id)
        if enabled_by_subject[subject_id]:
            candidates.append(question)
    if not candidates:
        return 0
    states = await states_for_questions(db, candidates)
    count = 0
    for question in candidates:
        if states.get(question.id) in ("draft", "accepted"):
            continue
        await enqueue_decompose(
            db, StructTargetType.QUESTION.value, question.id,
            priority=JobPriority.AUTO, user_id=user_id, subject_id=question.subject_id,
        )
        count += 1
    return count


async def after_questions_saved(
    db: AsyncSession, questions: Sequence[Question], *, user_id: Optional[int]
) -> None:
    """题目入库(新建、导入、审核通过)并提交之后调用:按开关排队拆解并提交。

    这是题目保存之后的附加动作,任何错误都只记日志,绝不影响题目本身的保存。
    """
    import logging

    try:
        if await auto_enqueue_questions(db, questions, user_id=user_id):
            await db.commit()
    except Exception:  # noqa: BLE001 - 自动拆解失败不能让题目保存失败
        await db.rollback()
        logging.getLogger(__name__).exception("Failed to queue automatic stem decomposition")


async def backfill_candidates(db: AsyncSession, subject_id: int, *, limit: int) -> List[int]:
    """学科内还没有任何拆解、也没有排队拆解的题目 id(按 id 升序,最多 limit 条)。"""
    has_run = exists().where(
        StructRun.target_type == StructTargetType.QUESTION.value,
        StructRun.target_id == Question.id,
        StructRun.state.in_([StructRunState.DRAFT.value, StructRunState.ACCEPTED.value]),
    )
    has_job = exists().where(
        Job.type == JOB_TYPE,
        Job.target_type == StructTargetType.QUESTION.value,
        Job.target_id == Question.id,
        Job.status.in_(ACTIVE_JOB_STATUSES),
    )
    rows = await db.execute(
        select(Question.id)
        .where(Question.subject_id == subject_id, Question.deleted_at.is_(None), ~has_run, ~has_job)
        .order_by(Question.id)
        .limit(limit)
    )
    return [row[0] for row in rows.all()]

# endregion


# region 序列化

async def serialize_run(
    db: AsyncSession, run: StructRun, *, current_revision: Optional[int] = None
) -> Dict[str, Any]:
    """拆解快照 → API 结构(含类型路径、设问依赖的条件 id、体检报告、是否过期)。"""
    paths = type_svc.path_names(await type_svc.list_types(db, run.subject_id)) if run.subject_id else {}
    report = json.loads(run.check_report) if run.check_report else None
    ref_ids = [e.ref_element_id for e in run.elements if e.ref_element_id]
    shared_sources: Dict[int, int] = {}
    if ref_ids:
        rows = await db.execute(
            select(StructElement.id, StructRun.target_id)
            .join(StructRun, StructElement.run_id == StructRun.id)
            .where(StructElement.id.in_(ref_ids))
        )
        shared_sources = {row[0]: row[1] for row in rows.all()}
    return {
        "id": run.id,
        "target_type": run.target_type,
        "target_id": run.target_id,
        "subject_id": run.subject_id,
        "source_revision": run.source_revision,
        "stale": is_stale(run, current_revision),
        "stem_text": run.stem_text,
        "origin": run.origin,
        "model": run.model,
        "prompt_version": run.prompt_version,
        "state": run.state,
        "check_report": report,
        "check_errors": run.check_errors or 0,
        "check_warnings": run.check_warnings or 0,
        "created_by": run.created_by,
        "reviewed_by": run.reviewed_by,
        "reviewed_at": run.reviewed_at,
        "created_at": run.created_at,
        "elements": [
            {
                "id": e.id,
                "ordinal": e.ordinal,
                "content": e.content,
                "type_id": e.type_id,
                "type_path": paths.get(e.type_id, []) if e.type_id else [],
                "type_hint": e.type_hint,
                "facet": e.facet,
                "span": [e.span_start, e.span_end] if e.span_start is not None else None,
                "ref_element_id": e.ref_element_id,
                "shared_from_stimulus_id": shared_sources.get(e.ref_element_id) if e.ref_element_id else None,
            }
            for e in run.elements
        ],
        "asks": [
            {
                "id": a.id,
                "ordinal": a.ordinal,
                "content": a.content,
                "type_id": a.type_id,
                "type_path": paths.get(a.type_id, []) if a.type_id else [],
                "type_hint": a.type_hint,
                "span": [a.span_start, a.span_end] if a.span_start is not None else None,
                "depends_on": sorted(link.element_id for link in a.element_links),
            }
            for a in run.asks
        ],
    }


async def structure_view(db: AsyncSession, target: Target) -> Dict[str, Any]:
    """一个对象的结构化全貌:当前采纳、待审草稿、进行中的 job、所属材料的拆解状态。"""
    from app.services.jobs import job_service

    accepted = await accepted_run(db, target.type, target.id)
    draft = await pending_draft(db, target.type, target.id)
    job = await active_job(db, target.type, target.id)
    queue_ahead = None
    if job is not None and job.status == JobStatus.PENDING.value:
        queue_ahead = (await job_service.queue_positions(db, [job.id])).get(job.id)
    return {
        "target_type": target.type,
        "target_id": target.id,
        "subject_id": target.subject_id,
        "current_revision": target.revision,
        "stimulus_id": target.stimulus_id,
        "enabled": await struct_settings.is_enabled(db),
        "accepted": await serialize_run(db, accepted, current_revision=target.revision) if accepted else None,
        "draft": await serialize_run(db, draft, current_revision=target.revision) if draft else None,
        "job": {
            "id": job.id,
            "status": job.status,
            "paused_reason": job.paused_reason,
            "error": job.error,
            "queue_ahead": queue_ahead,
        } if job else None,
    }


def state_of(accepted: Optional[StructRun], draft: Optional[StructRun], current_revision: Optional[int]) -> str:
    """列表徽标用的结构状态:none / draft / accepted / stale。"""
    if draft is not None:
        return "draft"
    if accepted is None:
        return "none"
    return "stale" if is_stale(accepted, current_revision) else "accepted"


async def states_for_questions(db: AsyncSession, questions: Sequence[Question]) -> Dict[int, str]:
    """一批题目的结构状态(题库列表徽标用,两次查询完成)。"""
    ids = [q.id for q in questions]
    if not ids:
        return {}
    rows = await db.execute(
        select(StructRun.target_id, StructRun.state, StructRun.source_revision)
        .where(
            StructRun.target_type == StructTargetType.QUESTION.value,
            StructRun.target_id.in_(ids),
            StructRun.state.in_([StructRunState.DRAFT.value, StructRunState.ACCEPTED.value]),
        )
    )
    has_draft: set = set()
    accepted_rev: Dict[int, int] = {}
    for target_id, state, revision in rows.all():
        if state == StructRunState.DRAFT.value:
            has_draft.add(target_id)
        else:
            accepted_rev[target_id] = revision or 1
    out: Dict[int, str] = {}
    for q in questions:
        if q.id in has_draft:
            out[q.id] = "draft"
        elif q.id in accepted_rev:
            out[q.id] = "stale" if accepted_rev[q.id] != (q.content_revision or 1) else "accepted"
        else:
            out[q.id] = "none"
    return out

# endregion


# region 同结构题与检索条件

async def similar_question_ids(
    db: AsyncSession, question: Question, *, limit: int = 10
) -> List[Dict[str, Any]]:
    """同结构题:同学科、已采纳拆解中,设问类型 + 条件类型集合与本题相近的题(Jaccard 相似度)。

    返回 [{"question_id", "score", "shared_type_ids"}],按相似度降序;本题没有已采纳拆解时为空。
    """
    run = await accepted_run(db, StructTargetType.QUESTION.value, question.id)
    if run is None:
        return []
    mine = {e.type_id for e in run.elements if e.type_id} | {a.type_id for a in run.asks if a.type_id}
    if not mine:
        return []
    candidate_types: Dict[int, set] = {}
    for model in (StructElement, StructAsk):
        rows = await db.execute(
            select(StructRun.target_id, model.type_id)
            .join(StructRun, model.run_id == StructRun.id)
            .where(
                StructRun.target_type == StructTargetType.QUESTION.value,
                StructRun.state == StructRunState.ACCEPTED.value,
                StructRun.subject_id == question.subject_id,
                StructRun.target_id != question.id,
                model.type_id.is_not(None),
            )
        )
        for target_id, type_id in rows.all():
            candidate_types.setdefault(target_id, set()).add(type_id)
    scored = []
    for target_id, theirs in candidate_types.items():
        shared = mine & theirs
        if not shared:
            continue
        score = len(shared) / len(mine | theirs)
        scored.append({"question_id": target_id, "score": round(score, 4), "shared_type_ids": sorted(shared)})
    scored.sort(key=lambda item: (-item["score"], item["question_id"]))
    return scored[:limit]


def question_type_filter(type_ids: Sequence[int]):
    """题目检索条件:已采纳拆解中有条件或设问属于这些类型(调用方负责展开子类型)。"""
    ids = list(set(type_ids))
    by_element = (
        select(StructRun.target_id)
        .join(StructElement, StructElement.run_id == StructRun.id)
        .where(
            StructRun.target_type == StructTargetType.QUESTION.value,
            StructRun.state == StructRunState.ACCEPTED.value,
            StructElement.type_id.in_(ids),
        )
    )
    by_ask = (
        select(StructRun.target_id)
        .join(StructAsk, StructAsk.run_id == StructRun.id)
        .where(
            StructRun.target_type == StructTargetType.QUESTION.value,
            StructRun.state == StructRunState.ACCEPTED.value,
            StructAsk.type_id.in_(ids),
        )
    )
    return or_(Question.id.in_(by_element), Question.id.in_(by_ask))


def question_state_filter(state: str):
    """题目检索条件:结构状态 none / draft / accepted / stale。未知取值返回 None(不过滤)。"""
    def run_exists(*conditions):
        return exists().where(
            StructRun.target_type == StructTargetType.QUESTION.value,
            StructRun.target_id == Question.id,
            *conditions,
        )

    draft = run_exists(StructRun.state == StructRunState.DRAFT.value)
    accepted_current = run_exists(
        StructRun.state == StructRunState.ACCEPTED.value,
        StructRun.source_revision == func.coalesce(Question.content_revision, 1),
    )
    accepted_stale = run_exists(
        StructRun.state == StructRunState.ACCEPTED.value,
        StructRun.source_revision != func.coalesce(Question.content_revision, 1),
    )
    accepted_any = run_exists(StructRun.state == StructRunState.ACCEPTED.value)
    if state == "none":
        return and_(~draft, ~accepted_any)
    if state == "draft":
        return draft
    if state == "accepted":
        return and_(~draft, accepted_current)
    if state == "stale":
        return and_(~draft, accepted_stale)
    return None

# endregion


# region 统计(首页卡片、组卷分布)

async def subject_stats(db: AsyncSession, subject_id: int, viewer: Any) -> Dict[str, Any]:
    """学科的结构化进度与元素类型覆盖(只统计当前用户可见、未删除的题)。

    返回:{"total", "states": {none, draft, accepted, stale}, "queued", "top_types": [...],
    "unclassified"}。``top_types`` 按引用题数降序,最多 15 个;``unclassified`` 是已采纳
    拆解中尚未归类的条件 / 设问条数(留给归纳)。
    """
    from app.crud.crud_question import visible_questions_filter

    base = [Question.subject_id == subject_id, Question.deleted_at.is_(None), visible_questions_filter(viewer)]
    total = await db.scalar(select(func.count(Question.id)).where(*base)) or 0
    states: Dict[str, int] = {}
    for state in ("draft", "accepted", "stale"):
        condition = question_state_filter(state)
        states[state] = await db.scalar(select(func.count(Question.id)).where(*base, condition)) or 0
    states["none"] = max(0, total - sum(states.values()))

    queued = await db.scalar(
        select(func.count(Job.id)).where(
            Job.type == JOB_TYPE, Job.subject_id == subject_id, Job.status.in_(ACTIVE_JOB_STATUSES)
        )
    ) or 0

    visible_ids = select(Question.id).where(*base)
    counts: Dict[int, set] = {}
    unclassified = 0
    for model in (StructElement, StructAsk):
        rows = await db.execute(
            select(StructRun.target_id, model.type_id)
            .join(StructRun, model.run_id == StructRun.id)
            .where(
                StructRun.target_type == StructTargetType.QUESTION.value,
                StructRun.state == StructRunState.ACCEPTED.value,
                StructRun.subject_id == subject_id,
                StructRun.target_id.in_(visible_ids),
            )
        )
        for target_id, type_id in rows.all():
            if type_id is None:
                unclassified += 1
            else:
                counts.setdefault(type_id, set()).add(target_id)
    types = await type_svc.list_types(db, subject_id)
    by_id = {t.id: t for t in types}
    paths = type_svc.path_names(types)
    top = sorted(counts.items(), key=lambda item: (-len(item[1]), item[0]))[:15]
    return {
        "total": total,
        "states": states,
        "queued": queued,
        "unclassified": unclassified,
        "top_types": [
            {
                "type_id": type_id,
                "kind": by_id[type_id].kind if type_id in by_id else None,
                "path": paths.get(type_id, []),
                "count": len(question_ids),
            }
            for type_id, question_ids in top
        ],
    }


async def type_distribution(db: AsyncSession, question_ids: Sequence[int], viewer: Any) -> Dict[str, Any]:
    """一组题(例如一份试卷)的元素类型分布:按领域(类型树第一层)与具体类型统计题数。

    返回:{"questions", "structured", "domains": [{type_id, name, kind, count}],
    "types": [{type_id, path, kind, count}]};题数按「至少一个条件 / 设问属于该类型」计。
    """
    from app.crud.crud_question import visible_questions_filter

    ids = list(dict.fromkeys(question_ids))
    if not ids:
        return {"questions": 0, "structured": 0, "domains": [], "types": []}
    visible = select(Question.id).where(
        Question.id.in_(ids), Question.deleted_at.is_(None), visible_questions_filter(viewer)
    )
    leaf_counts: Dict[int, set] = {}
    structured: set = set()
    subject_ids: set = set()
    for model in (StructElement, StructAsk):
        rows = await db.execute(
            select(StructRun.target_id, StructRun.subject_id, model.type_id)
            .join(StructRun, model.run_id == StructRun.id)
            .where(
                StructRun.target_type == StructTargetType.QUESTION.value,
                StructRun.state == StructRunState.ACCEPTED.value,
                StructRun.target_id.in_(visible),
            )
        )
        for target_id, subject_id, type_id in rows.all():
            structured.add(target_id)
            if subject_id is not None:
                subject_ids.add(subject_id)
            if type_id is not None:
                leaf_counts.setdefault(type_id, set()).add(target_id)
    types: List[StructType] = []
    for subject_id in subject_ids:
        types.extend(await type_svc.list_types(db, subject_id))
    by_id = {t.id: t for t in types}
    paths = type_svc.path_names(types)

    def root_of(type_id: int) -> Optional[StructType]:
        current = by_id.get(type_id)
        guard = 0
        while current is not None and current.parent_id and guard < 64:
            current = by_id.get(current.parent_id)
            guard += 1
        return current

    domain_counts: Dict[int, set] = {}
    for type_id, targets in leaf_counts.items():
        root = root_of(type_id)
        if root is not None:
            domain_counts.setdefault(root.id, set()).update(targets)
    return {
        "questions": len(ids),
        "structured": len(structured),
        "domains": sorted(
            (
                {"type_id": t_id, "name": by_id[t_id].name, "kind": by_id[t_id].kind, "count": len(targets)}
                for t_id, targets in domain_counts.items()
                if t_id in by_id
            ),
            key=lambda item: (-item["count"], item["type_id"]),
        ),
        "types": sorted(
            (
                {"type_id": t_id, "path": paths.get(t_id, []), "kind": by_id[t_id].kind, "count": len(targets)}
                for t_id, targets in leaf_counts.items()
                if t_id in by_id
            ),
            key=lambda item: (-item["count"], item["type_id"]),
        ),
    }

# endregion


# region 内部实现

def _run_query():
    """带出条件、设问与设问依赖的拆解查询。"""
    return select(StructRun).options(
        selectinload(StructRun.elements),
        selectinload(StructRun.asks).selectinload(StructAsk.element_links),
    )


async def _allowed_type_ids(db: AsyncSession, subject_id: Optional[int]) -> Dict[int, str]:
    """学科内的类型:{id: kind}(人工保存时校验所选类型属于本学科)。"""
    if subject_id is None:
        return {}
    rows = await db.execute(select(StructType.id, StructType.kind).where(StructType.subject_id == subject_id))
    return {row[0]: row[1] for row in rows.all()}


def _checked_type(type_id: Any, allowed: Dict[int, str], kind: StructTypeKind) -> Optional[int]:
    if type_id in (None, ""):
        return None
    try:
        type_id = int(type_id)
    except (TypeError, ValueError):
        raise Invalid("Invalid structure type", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
    if allowed.get(type_id) != kind.value:
        raise Invalid("Invalid structure type", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
    return type_id


def _required_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise Invalid("Item content is required", ErrorCode.STRUCTURE_INVALID_ITEM)
    return text


def _span(item: Dict[str, Any], stem_text: str) -> Optional[tuple]:
    """人工给出的原文区间;越界或不完整时视为未给出(由体检按引文重新定位)。"""
    start, end = item.get("span_start"), item.get("span_end")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(stem_text):
        return start, end
    return None


# region 参数槽与元素组:旋钮式条件重组与原创命题
# 与上游 struct_* 表不冲突,全部旁挂;写入不提交,由调用方掌控事务。


async def create_struct_param(
    db: AsyncSession,
    *,
    element_id: int,
    name: str,
    value_text: str,
    slot_kind: Optional[str] = None,
    domain: Optional[str] = None,
    replaceable: bool = True,
) -> StructParam:
    """在元素上新建一个参数槽。"""
    param = StructParam(
        element_id=element_id,
        name=name.strip(),
        value_text=value_text,
        slot_kind=slot_kind,
        domain=domain,
        replaceable=1 if replaceable else 0,
    )
    db.add(param)
    await db.flush()
    return param


async def get_struct_param(db: AsyncSession, param_id: int) -> StructParam:
    """按 id 取参数槽,不存在抛 NotFound。"""
    param = await db.get(StructParam, param_id)
    if param is None:
        raise NotFound("Structure param not found", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
    return param


async def list_struct_params(
    db: AsyncSession, element_id: Optional[int] = None, *, replaceable_only: bool = False
) -> List[StructParam]:
    """取参数槽,可按元素过滤,可只取可替换的。"""
    stmt = select(StructParam)
    if element_id is not None:
        stmt = stmt.where(StructParam.element_id == element_id)
    if replaceable_only:
        stmt = stmt.where(StructParam.replaceable == 1)
    stmt = stmt.order_by(StructParam.id)
    return list((await db.execute(stmt)).scalars().all())


async def update_struct_param(
    db: AsyncSession, param_id: int, **values: Any
) -> StructParam:
    """更新参数槽字段,仅允许 name/value_text/slot_kind/domain/replaceable。"""
    allowed = {"name", "value_text", "slot_kind", "domain", "replaceable"}
    param = await get_struct_param(db, param_id)
    for key, val in values.items():
        if key not in allowed:
            raise Invalid(f"Unknown param field: {key}", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
        if key == "replaceable":
            val = 1 if val else 0
        if key in ("name", "value_text") and isinstance(val, str):
            val = val.strip()
        setattr(param, key, val)
    await db.flush()
    return param


async def delete_struct_param(db: AsyncSession, param_id: int) -> None:
    """删除参数槽。"""
    param = await get_struct_param(db, param_id)
    await db.delete(param)
    await db.flush()


async def create_element_group(
    db: AsyncSession,
    *,
    run_id: int,
    name: str,
    description: Optional[str] = None,
    replaceable: bool = True,
    sort_order: int = 0,
) -> StructElementGroup:
    """在一个拆解快照下新建元素组。"""
    group = StructElementGroup(
        run_id=run_id,
        name=name.strip(),
        description=description,
        replaceable=1 if replaceable else 0,
        sort_order=sort_order,
    )
    db.add(group)
    await db.flush()
    return group


async def get_element_group(db: AsyncSession, group_id: int) -> StructElementGroup:
    """按 id 取元素组,不存在抛 NotFound。"""
    group = await db.get(StructElementGroup, group_id)
    if group is None:
        raise NotFound("Structure element group not found", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
    return group


async def list_element_groups(db: AsyncSession, run_id: int) -> List[StructElementGroup]:
    """取一个快照下的全部元素组(按排序号、id)。"""
    stmt = (
        select(StructElementGroup)
        .where(StructElementGroup.run_id == run_id)
        .order_by(StructElementGroup.sort_order, StructElementGroup.id)
    )
    return list((await db.execute(stmt)).scalars().all())


async def update_element_group(db: AsyncSession, group_id: int, **values: Any) -> StructElementGroup:
    """更新元素组字段。"""
    allowed = {"name", "description", "replaceable", "sort_order"}
    group = await get_element_group(db, group_id)
    for key, val in values.items():
        if key not in allowed:
            raise Invalid(f"Unknown group field: {key}", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
        if key == "replaceable":
            val = 1 if val else 0
        if key == "name" and isinstance(val, str):
            val = val.strip()
        setattr(group, key, val)
    await db.flush()
    return group


async def delete_element_group(db: AsyncSession, group_id: int) -> None:
    """删除元素组及其关联项(cascade)。"""
    group = await get_element_group(db, group_id)
    await db.delete(group)
    await db.flush()


async def add_group_item(db: AsyncSession, *, group_id: int, element_id: int) -> StructElementGroupItem:
    """把元素加入元素组。"""
    await get_element_group(db, group_id)
    item = StructElementGroupItem(group_id=group_id, element_id=element_id)
    db.add(item)
    await db.flush()
    return item


async def remove_group_item(db: AsyncSession, *, group_id: int, element_id: int) -> None:
    """从元素组移出元素。"""
    stmt = select(StructElementGroupItem).where(
        StructElementGroupItem.group_id == group_id,
        StructElementGroupItem.element_id == element_id,
    )
    item = (await db.execute(stmt)).scalar_one_or_none()
    if item is None:
        raise NotFound("Group item not found", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
    await db.delete(item)
    await db.flush()


async def list_group_items(db: AsyncSession, group_id: int) -> List[StructElement]:
    """取元素组包含的全部元素(按元素 ordinal)。"""
    await get_element_group(db, group_id)
    stmt = (
        select(StructElement)
        .join(StructElementGroupItem, StructElement.id == StructElementGroupItem.element_id)
        .where(StructElementGroupItem.group_id == group_id)
        .order_by(StructElement.ordinal)
    )
    return list((await db.execute(stmt)).scalars().all())


async def list_replaceable_params(
    db: AsyncSession, run_id: int
) -> List[StructParam]:
    """取一个快照下全部可替换的参数槽(带所属元素内容),用于变式生成。"""
    stmt = (
        select(StructParam)
        .join(StructElement, StructParam.element_id == StructElement.id)
        .where(StructElement.run_id == run_id, StructParam.replaceable == 1)
        .order_by(StructElement.ordinal, StructParam.id)
    )
    return list((await db.execute(stmt)).scalars().all())


def apply_param_values_to_stem(
    stem_text: str,
    assignments: Dict[int, str],
    params_by_id: Dict[int, StructParam],
) -> str:
    """把参数槽新值应用到题干快照上,生成变式题干文本。

    以参数槽的 value_text 作为旧值在 stem_text 中做逐字替换;同一旧值出现多处时全部替换。
    仅替换 assignments 里给出的槽位,未给出的保持原值。
    """
    result = stem_text
    for param_id, new_value in assignments.items():
        param = params_by_id.get(param_id)
        if param is None:
            continue
        old_value = param.value_text
        if old_value and old_value != new_value:
            result = result.replace(old_value, new_value)
    return result


# endregion

