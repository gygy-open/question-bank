"""元素归纳(规格二期):把尚未归类的条件 / 设问聚成候选类型,老师确认后进入类型树。

流程:
1. **收集**:学科内已采纳拆解中 ``type_id`` 为空的条件与设问(引用材料的条件、已被老师
   忽略过的条目除外)。条件与设问分开归纳。
2. **粗分组**:按规范化后的 ``type_hint`` 分组(拆解时 AI 已按题干语言写了类别描述);
   没有 hint 的条目各成一组。组数超过上限时只取最大的若干组,其余留给下一次归纳。
3. **AI 合并**:把各组(hint、条数、示例)交给 AI,合并成候选类型,并建议父节点与相似的
   已有类型。体检要求每组恰好归入一个候选;有遗漏时带着问题重试一次,仍遗漏的组各自成为
   候选(名称取 hint),保证不丢数据。
4. **保存**:覆盖该学科、该 kind 之前所有 pending 候选。
5. **确认**(站内,学科内有类型维护权限的人):新建为类型 / 并入已有类型 / 忽略。新建或并入
   时,组内仍未归类的条目原地回填 ``type_id``——类型是分类元数据,不生成新快照。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.capabilities.errors import Invalid, NotFound
from app.core.api_errors import ErrorCode
from app.crud.crud_subject_prompt import subject_prompt as crud_subject_prompt
from app.models.import_task import ImportPauseReason
from app.models.job import ACTIVE_JOB_STATUSES, Job, JobPriority
from app.models.question_structure import (
    StructAsk,
    StructCandidateStatus,
    StructElement,
    StructRun,
    StructRunState,
    StructType,
    StructTypeCandidate,
    StructTypeCandidateItem,
    StructTypeKind,
    StructTypeStatus,
)
from app.models.subject import Subject
from app.services.jobs import JobContext, JobHandler, JobStopped, register_handler
from app.services.prompt_utils import apply_output_language, render_subject_prompt
from app.services.prompts import get_default_prompt

from . import settings as struct_settings
from . import types as type_svc

logger = logging.getLogger(__name__)

JOB_TYPE = "struct_type.induce"
JOB_TARGET_TYPE = "subject"
PROMPT_KEY = "AI_STRUCT_INDUCE_PROMPT"
# 未归类条目少于此数时不归纳:样本太少,聚类没有意义。
MIN_ITEMS = 10
# 一次交给 AI 的组数上限(按组大小取前若干组),控制提示词长度。
MAX_GROUPS = 200
EXAMPLES_PER_GROUP = 3
RETRY_ON_MISSING_GROUPS = 1

ERROR_NOT_ENOUGH_DATA = "not_enough_data"
ERROR_DISABLED = "structure_disabled"


@dataclass
class Unclassified:
    """一条未归类的条件或设问。"""

    kind: str
    id: int
    content: str
    hint: Optional[str]


@dataclass
class HintGroup:
    """type_hint 相同(规范化后)的一组未归类条目。"""

    label: str
    items: List[Unclassified] = field(default_factory=list)


@dataclass
class CandidateDraft:
    """AI 提出的一个候选类型(尚未落库)。"""

    name: str
    definition: Optional[str]
    parent_id: Optional[int]
    similar_type_id: Optional[int]
    groups: List[int]


# region AI 输出的宽松解析模型

class _AICandidate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = ""
    definition: Optional[str] = None
    parent: Optional[str] = None
    similar: Optional[str] = None
    groups: List[int] = Field(default_factory=list)

    @field_validator("name", mode="before")
    @classmethod
    def _text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @field_validator("definition", "parent", "similar", mode="before")
    @classmethod
    def _optional_text(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return None if text.lower() in ("", "null", "none") else text

    @field_validator("groups", mode="before")
    @classmethod
    def _indices(cls, value: Any) -> List[int]:
        if not isinstance(value, list):
            return []
        out: List[int] = []
        for item in value:
            text = str(item).strip().lstrip("gG")
            if text.isdigit():
                out.append(int(text))
        return out


class _AIOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidates: List[_AICandidate] = Field(default_factory=list)

# endregion


# region 收集与分组

async def unclassified_items(db: AsyncSession, subject_id: int, kind: str) -> List[Unclassified]:
    """学科内已采纳拆解中未归类的条件(kind=condition)或设问(kind=ask)。

    引用材料的条件不算(它们只是材料条件的副本);老师忽略过的候选中的条目也不再参与。
    """
    ignored = (
        select(StructTypeCandidateItem.element_id if kind == StructTypeKind.CONDITION.value else StructTypeCandidateItem.ask_id)
        .join(StructTypeCandidate, StructTypeCandidate.id == StructTypeCandidateItem.candidate_id)
        .where(
            StructTypeCandidate.subject_id == subject_id,
            StructTypeCandidate.status == StructCandidateStatus.IGNORED.value,
        )
    )
    if kind == StructTypeKind.CONDITION.value:
        model: Any = StructElement
        extra = [StructElement.ref_element_id.is_(None)]
    else:
        model = StructAsk
        extra = []
    rows = await db.execute(
        select(model.id, model.content, model.type_hint)
        .join(StructRun, model.run_id == StructRun.id)
        .where(
            StructRun.subject_id == subject_id,
            StructRun.state == StructRunState.ACCEPTED.value,
            model.type_id.is_(None),
            model.id.not_in(ignored),
            *extra,
        )
        .order_by(model.id)
    )
    return [Unclassified(kind=kind, id=row[0], content=row[1], hint=row[2]) for row in rows.all()]


async def unclassified_counts(db: AsyncSession, subject_id: int) -> Dict[str, int]:
    """各 kind 的未归类条目数(类型管理页展示、判断能否归纳)。"""
    return {
        kind.value: len(await unclassified_items(db, subject_id, kind.value))
        for kind in (StructTypeKind.CONDITION, StructTypeKind.ASK)
    }


def group_by_hint(items: Sequence[Unclassified], *, limit: int = MAX_GROUPS) -> List[HintGroup]:
    """按规范化后的 type_hint 粗分组,组按条数降序,最多 ``limit`` 组。没有 hint 的条目各成一组。"""
    groups: Dict[str, HintGroup] = {}
    for item in items:
        hint = (item.hint or "").strip()
        key = _normalize_hint(hint) if hint else f"#{item.id}"
        group = groups.setdefault(key, HintGroup(label=hint or item.content[:60]))
        group.items.append(item)
    ordered = sorted(groups.values(), key=lambda g: (-len(g.items), g.items[0].id))
    return ordered[:limit]

# endregion


# region 调用 AI

async def induce(
    db: AsyncSession,
    *,
    subject_id: int,
    kind: str,
    groups: Sequence[HintGroup],
    user_id: Optional[int],
) -> tuple[List[CandidateDraft], Optional[int]]:
    """让 AI 把各组合并成候选类型。返回 (候选, 服务商 id)。

    :raises ModelNotConfigured: 没有可用的文本模型。
    :raises Exception: AI 调用错误原样抛出,由调用方按 ai_errors 分类。
    """
    from app.services.ai_errors import with_ai_retry
    from app.services.ai_provider import get_ai_provider
    from app.services.ai_resolver import resolve_model

    from .decompose import ModelNotConfigured

    resolved = await resolve_model(db, user_id=user_id, purpose="text")
    if resolved is None:
        raise ModelNotConfigured()
    provider = get_ai_provider(resolved.interface_type)
    types = await type_svc.list_types(db, subject_id)
    system = await build_system_prompt(db, subject_id=subject_id, kind=kind, types=types)

    feedback: List[str] = []
    drafts: List[CandidateDraft] = []
    for attempt in range(RETRY_ON_MISSING_GROUPS + 1):
        user = build_user_message(groups, feedback)
        raw = await with_ai_retry(lambda: provider.generate_json(system, user, resolved.config))
        drafts, missing = parse_output(raw, groups=groups, types=types, kind=kind)
        if not missing:
            break
        feedback = [f"groups {', '.join(f'g{i}' for i in missing)} are not assigned to any candidate"]
        logger.info("Type induction attempt %d left %d group(s) unassigned", attempt + 1, len(missing))
    else:
        # 重试后仍有遗漏:遗漏的组各自成为候选,保证每条未归类条目都能被老师看到。
        for index in missing:
            drafts.append(CandidateDraft(
                name=groups[index].label[:128], definition=None, parent_id=None, similar_type_id=None, groups=[index]
            ))
    return drafts, resolved.provider.id


async def build_system_prompt(
    db: AsyncSession, *, subject_id: int, kind: str, types: Sequence[StructType]
) -> str:
    """系统提示词(学科覆盖 → 代码默认),注入本 kind 的类型树。"""
    subject = await db.get(Subject, subject_id)
    override = await crud_subject_prompt.get_value(db, subject_id, PROMPT_KEY)
    template = override if override is not None else get_default_prompt(PROMPT_KEY)
    prompt = render_subject_prompt(template, subject) or ""
    tree = type_svc.tree_text(types, StructTypeKind(kind)) or "(none yet)"
    item_kind = "conditions (given facts and objects)" if kind == StructTypeKind.CONDITION.value else "asks (what the question requires)"
    prompt = prompt.replace("{type_tree}", tree).replace("{item_kind}", item_kind)
    return apply_output_language(prompt, "extract")


def build_user_message(groups: Sequence[HintGroup], feedback: Sequence[str]) -> str:
    """本次输入:各组的 hint、条数与示例;上一次结果的问题清单。"""
    lines = []
    for index, group in enumerate(groups):
        examples = " | ".join(item.content for item in group.items[:EXAMPLES_PER_GROUP])
        lines.append(f"g{index}: {group.label} ({len(group.items)} items) e.g. {examples}")
    parts = ["## Groups\n" + "\n".join(lines)]
    if feedback:
        parts.append("## Problems in your previous answer - fix them\n" + "\n".join(f"- {line}" for line in feedback))
    return "\n\n".join(parts)


def parse_output(
    raw: Any, *, groups: Sequence[HintGroup], types: Sequence[StructType], kind: str
) -> tuple[List[CandidateDraft], List[int]]:
    """模型输出 → 候选。越界的组号忽略,重复出现的组只算第一次。返回 (候选, 未分配的组号)。

    父节点 / 相似类型只接受本 kind 的类型 code;未知 code 视为未给出。
    整体不是对象时抛 ``ValueError``(由 ai_errors 归为文档类错误)。
    """
    if isinstance(raw, list):
        raw = {"candidates": raw}
    if not isinstance(raw, dict):
        raise ValueError("Induction output is not a JSON object")
    output = _AIOutput.model_validate(raw)
    by_code = {t.code: t.id for t in types if t.kind == kind and t.status != StructTypeStatus.DEPRECATED.value}
    assigned: set = set()
    drafts: List[CandidateDraft] = []
    for item in output.candidates:
        indices = [i for i in dict.fromkeys(item.groups) if 0 <= i < len(groups) and i not in assigned]
        if not indices:
            continue
        assigned.update(indices)
        name = item.name or groups[indices[0]].label
        drafts.append(CandidateDraft(
            name=name[:128],
            definition=item.definition,
            parent_id=by_code.get(item.parent) if item.parent else None,
            similar_type_id=by_code.get(item.similar) if item.similar else None,
            groups=indices,
        ))
    missing = [i for i in range(len(groups)) if i not in assigned]
    return drafts, missing

# endregion


# region 保存与确认

async def save_candidates(
    db: AsyncSession,
    *,
    subject_id: int,
    kind: str,
    drafts: Sequence[CandidateDraft],
    groups: Sequence[HintGroup],
    job_id: Optional[int],
) -> int:
    """覆盖保存一个 kind 的候选(flush,不提交):先删掉该学科、该 kind 原有的 pending 候选。"""
    await db.execute(
        delete(StructTypeCandidate).where(
            StructTypeCandidate.subject_id == subject_id,
            StructTypeCandidate.kind == kind,
            StructTypeCandidate.status == StructCandidateStatus.PENDING.value,
        )
    )
    is_condition = kind == StructTypeKind.CONDITION.value
    for draft in drafts:
        candidate = StructTypeCandidate(
            subject_id=subject_id,
            kind=kind,
            name=draft.name,
            definition=draft.definition,
            suggested_parent_id=draft.parent_id,
            similar_type_id=draft.similar_type_id,
            status=StructCandidateStatus.PENDING.value,
            job_id=job_id,
        )
        for index in draft.groups:
            for item in groups[index].items:
                candidate.items.append(
                    StructTypeCandidateItem(element_id=item.id if is_condition else None, ask_id=None if is_condition else item.id)
                )
        db.add(candidate)
    await db.flush()
    return len(drafts)


async def get_candidate(db: AsyncSession, candidate_id: int) -> StructTypeCandidate:
    candidate = await db.scalar(
        select(StructTypeCandidate)
        .options(selectinload(StructTypeCandidate.items))
        .where(StructTypeCandidate.id == candidate_id)
    )
    if candidate is None:
        raise NotFound("Candidate not found", ErrorCode.STRUCTURE_CANDIDATE_NOT_FOUND)
    return candidate


async def accept_candidate(
    db: AsyncSession,
    candidate: StructTypeCandidate,
    *,
    name: Optional[str],
    parent_id: Optional[int],
    definition: Optional[str],
    user_id: Optional[int],
) -> StructType:
    """新建为类型(启用),回填组内条目,提交。父节点缺省时用 AI 建议的,再缺省时挂在 kind 的根下。"""
    _ensure_pending(candidate)
    parent_id = parent_id or candidate.suggested_parent_id or await _default_parent(db, candidate)
    created = await type_svc.create_type(
        db,
        subject_id=candidate.subject_id,
        name=(name or candidate.name).strip(),
        kind=candidate.kind,
        parent_id=parent_id,
        definition=definition if definition is not None else candidate.definition,
        created_by=user_id,
    )
    await _resolve(db, candidate, created.id, StructCandidateStatus.ACCEPTED, user_id)
    return created


async def merge_candidate(
    db: AsyncSession, candidate: StructTypeCandidate, *, type_id: int, user_id: Optional[int]
) -> StructType:
    """并入已有类型(同学科、同 kind),回填组内条目,提交。"""
    _ensure_pending(candidate)
    target = await type_svc.get_type(db, type_id)
    if target.subject_id != candidate.subject_id or target.kind != candidate.kind:
        raise Invalid("Type does not match the candidate", ErrorCode.STRUCTURE_TYPE_NOT_FOUND)
    await _resolve(db, candidate, target.id, StructCandidateStatus.MERGED, user_id)
    return target


async def ignore_candidate(db: AsyncSession, candidate: StructTypeCandidate, *, user_id: Optional[int]) -> None:
    """忽略候选:组内条目保持未归类,且之后的归纳不再收集它们。提交。"""
    _ensure_pending(candidate)
    candidate.status = StructCandidateStatus.IGNORED.value
    candidate.resolved_by = user_id
    candidate.resolved_at = datetime.utcnow()
    await db.commit()


async def list_candidates(db: AsyncSession, subject_id: int, viewer: Any) -> List[Dict[str, Any]]:
    """学科的 pending 候选(按条数降序),每个带最多 5 条示例与类型路径。

    示例只取 ``viewer`` 可见的题目 / 材料中的条目(条数统计不受影响,不泄露内容)。
    """
    candidates = (
        await db.execute(
            select(StructTypeCandidate)
            .options(selectinload(StructTypeCandidate.items))
            .where(
                StructTypeCandidate.subject_id == subject_id,
                StructTypeCandidate.status == StructCandidateStatus.PENDING.value,
            )
        )
    ).scalars().all()
    if not candidates:
        return []
    element_ids = [i.element_id for c in candidates for i in c.items if i.element_id]
    ask_ids = [i.ask_id for c in candidates for i in c.items if i.ask_id]
    contents: Dict[tuple, str] = {}
    unresolved: set = set()
    targets: Dict[tuple, tuple] = {}
    for model, ids, key in ((StructElement, element_ids, "e"), (StructAsk, ask_ids, "a")):
        if not ids:
            continue
        rows = await db.execute(
            select(model.id, model.content, model.type_id, StructRun.target_type, StructRun.target_id)
            .join(StructRun, model.run_id == StructRun.id)
            .where(model.id.in_(ids))
        )
        for item_id, content, type_id, target_type, target_id in rows.all():
            contents[(key, item_id)] = content
            targets[(key, item_id)] = (target_type, target_id)
            if type_id is None:
                unresolved.add((key, item_id))
    visible = await _visible_targets(db, set(targets.values()), viewer)
    paths = type_svc.path_names(await type_svc.list_types(db, subject_id))
    out = []
    for candidate in candidates:
        keys = [("e", i.element_id) if i.element_id else ("a", i.ask_id) for i in candidate.items]
        # 期间被老师在面板里手动归类的条目不再计入。
        keys = [k for k in keys if k in unresolved]
        out.append({
            "id": candidate.id,
            "kind": candidate.kind,
            "name": candidate.name,
            "definition": candidate.definition,
            "count": len(keys),
            "samples": [contents[k] for k in keys if targets[k] in visible][:5],
            "suggested_parent_id": candidate.suggested_parent_id,
            "suggested_parent_path": paths.get(candidate.suggested_parent_id, []) if candidate.suggested_parent_id else [],
            "similar_type_id": candidate.similar_type_id,
            "similar_type_path": paths.get(candidate.similar_type_id, []) if candidate.similar_type_id else [],
            "created_at": candidate.created_at,
        })
    out.sort(key=lambda item: (-item["count"], item["id"]))
    return [item for item in out if item["count"] > 0]


async def active_job(db: AsyncSession, subject_id: int) -> Optional[Job]:
    """学科未结束的归纳 job。"""
    return await db.scalar(
        select(Job)
        .where(
            Job.type == JOB_TYPE,
            Job.target_type == JOB_TARGET_TYPE,
            Job.target_id == subject_id,
            Job.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(Job.id.desc())
        .limit(1)
    )


async def last_job(db: AsyncSession, subject_id: int) -> Optional[Job]:
    """学科最近一次归纳 job(任意状态)。"""
    return await db.scalar(
        select(Job)
        .where(Job.type == JOB_TYPE, Job.target_type == JOB_TARGET_TYPE, Job.target_id == subject_id)
        .order_by(Job.id.desc())
        .limit(1)
    )


async def enqueue(db: AsyncSession, subject_id: int, *, user_id: Optional[int], locale: Optional[str]) -> Job:
    """排队归纳(已有未结束的 job 时复用)。不提交。"""
    from app.services.jobs import job_service

    return await job_service.enqueue(
        db,
        type=JOB_TYPE,
        target_type=JOB_TARGET_TYPE,
        target_id=subject_id,
        priority=JobPriority.USER,
        user_id=user_id,
        subject_id=subject_id,
        locale=locale,
    )

# endregion


# region job 处理器

@register_handler
class InduceJobHandler(JobHandler):
    """对一个学科做一次元素归纳(条件与设问各一次)。"""

    type = JOB_TYPE
    target_type = JOB_TARGET_TYPE

    async def run(self, ctx: JobContext) -> None:
        from app.services.ai_resolver import resolve_provider_id

        from .decompose import ModelNotConfigured

        db = ctx.db
        subject_id = ctx.target_id or 0
        if not await struct_settings.is_enabled(db):
            await ctx.fail("Question structure is disabled", error_code=ERROR_DISABLED)
            return
        await type_svc.ensure_roots(db, subject_id)
        pending: Dict[str, List[HintGroup]] = {}
        for kind in (StructTypeKind.CONDITION.value, StructTypeKind.ASK.value):
            items = await unclassified_items(db, subject_id, kind)
            if len(items) >= MIN_ITEMS:
                pending[kind] = group_by_hint(items)
        if not pending:
            await ctx.fail("Not enough unclassified items to induce types", error_code=ERROR_NOT_ENOUGH_DATA)
            return

        provider_id = await resolve_provider_id(db, user_id=ctx.user_id, purpose="text")
        if provider_id is None:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return

        results: Dict[str, tuple] = {}
        try:
            for kind, groups in pending.items():
                await ctx.set_progress(stage="inducing", kind=kind)
                drafts, used_provider = await induce(
                    db, subject_id=subject_id, kind=kind, groups=groups, user_id=ctx.user_id
                )
                results[kind] = (drafts, groups)
                provider_id = used_provider or provider_id
        except ModelNotConfigured:
            await ctx.pause(ImportPauseReason.MODEL, None, "No AI model is configured")
            return
        except JobStopped:
            raise
        except Exception as exc:  # noqa: BLE001 - 按 AI 错误类别暂停或失败
            logger.exception("Induce job %s failed", ctx.job_id)
            await ctx.handle_ai_error(exc, provider_id=provider_id)
            return

        await ctx.ai_succeeded(provider_id)
        counts = {kind: len(drafts) for kind, (drafts, _) in results.items()}
        await ctx.succeed(progress={"stage": "done", "candidates": counts}, provider_id=provider_id)
        for kind, (drafts, groups) in results.items():
            await save_candidates(db, subject_id=subject_id, kind=kind, drafts=drafts, groups=groups, job_id=ctx.job_id)
        await db.commit()
        logger.info("Induce job %s: subject %s -> %s candidate(s)", ctx.job_id, subject_id, counts)

# endregion


# region 内部实现

async def _visible_targets(db: AsyncSession, targets: set, viewer: Any) -> set:
    """一批拆解对象中 ``viewer`` 可见的 (target_type, target_id)。"""
    from app.crud.crud_question import is_question_visible
    from app.models.question import Question
    from app.models.stimulus import Stimulus

    out: set = set()
    for target_type, model in (("question", Question), ("stimulus", Stimulus)):
        ids = [target_id for t, target_id in targets if t == target_type]
        if not ids:
            continue
        objs = (await db.execute(select(model).where(model.id.in_(ids), model.deleted_at.is_(None)))).scalars().all()
        out.update((target_type, obj.id) for obj in objs if is_question_visible(obj, viewer))
    return out


def _normalize_hint(hint: str) -> str:
    return re.sub(r"\s+", " ", hint).strip().lower()


def _ensure_pending(candidate: StructTypeCandidate) -> None:
    if candidate.status != StructCandidateStatus.PENDING.value:
        raise Invalid("Candidate has already been resolved", ErrorCode.STRUCTURE_CANDIDATE_RESOLVED)


async def _default_parent(db: AsyncSession, candidate: StructTypeCandidate) -> Optional[int]:
    """候选没有建议父节点时:挂在该 kind 的第一个根下。"""
    await type_svc.ensure_roots(db, candidate.subject_id)
    return await db.scalar(
        select(StructType.id)
        .where(
            StructType.subject_id == candidate.subject_id,
            StructType.kind == candidate.kind,
            StructType.parent_id.is_(None),
        )
        .order_by(StructType.sort_order, StructType.id)
        .limit(1)
    )


async def _resolve(
    db: AsyncSession, candidate: StructTypeCandidate, type_id: int, status: StructCandidateStatus, user_id: Optional[int]
) -> None:
    """回填组内仍未归类的条目,记下候选的处理结果,提交。"""
    element_ids = [i.element_id for i in candidate.items if i.element_id]
    ask_ids = [i.ask_id for i in candidate.items if i.ask_id]
    for model, ids in ((StructElement, element_ids), (StructAsk, ask_ids)):
        if ids:
            await db.execute(
                update(model)
                .where(model.id.in_(ids), model.type_id.is_(None))
                .values(type_id=type_id)
                .execution_options(synchronize_session=False)
            )
    candidate.status = status.value
    candidate.resolved_type_id = type_id
    candidate.resolved_by = user_id
    candidate.resolved_at = datetime.utcnow()
    await db.commit()

# endregion
