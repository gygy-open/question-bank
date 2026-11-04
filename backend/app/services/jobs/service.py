"""jobs 表的读写:入队、领取、状态流转、按 AI 服务商暂停与恢复、取消、删除。

所有状态变化都经过这里,并在同一事务内调用处理器的 ``project`` 把执行状态同步
到业务表(例如导入任务的「排队中 / 处理中 / 已暂停」)。这样业务表上看到的状态
永远和 jobs 一致,业务代码也不需要自己维护队列逻辑。

本模块只写入、不提交,除非函数说明里写了「会提交」——事务由调用方掌控。
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import ColumnElement, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_task import ImportPauseReason
from app.models.job import ACTIVE_JOB_STATUSES, Job, JobPriority, JobStatus

from .registry import get_handler, registered_types

logger = logging.getLogger(__name__)

# 服务不可达而暂停的 job,隔这么久自动放回队列试探一次。
UNAVAILABLE_RETRY_AFTER = timedelta(minutes=5)
# 批量更新时每批的 id 数量:SQLite 对单条语句的参数个数有上限。
_CHUNK = 500

# 一行 job 的最小信息:(id, type, target_id),用于投影到业务表。
_JobRow = Tuple[int, str, Optional[int]]


# region 入队与重新排队

async def enqueue(
    db: AsyncSession,
    *,
    type: str,
    target_type: Optional[str] = None,
    target_id: Optional[int] = None,
    priority: int = JobPriority.USER,
    payload: Optional[Dict[str, Any]] = None,
    user_id: Optional[int] = None,
    subject_id: Optional[int] = None,
    locale: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    max_attempts: int = 1,
    run_after: Optional[datetime] = None,
) -> Job:
    """创建一条待执行的 job,返回它(已 flush,有 id)。

    去重规则:
    - 给了 ``idempotency_key`` 且已存在同键 job 时,直接返回已有的那条;
    - 同一业务记录(type + target)已有未结束的 job 时,直接返回它,不重复排队。
      若新请求的优先级更高,顺带把已有 job 的优先级提上来(例如回填中的题被用户手动点了「拆解」)。
    """
    if idempotency_key:
        existing = await db.scalar(select(Job).where(Job.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
    if target_type is not None and target_id is not None:
        active = await db.scalar(
            select(Job)
            .where(
                Job.type == type,
                Job.target_type == target_type,
                Job.target_id == target_id,
                Job.status.in_(ACTIVE_JOB_STATUSES),
            )
            .order_by(Job.id.desc())
            .limit(1)
        )
        if active is not None:
            if priority > (active.priority or 0):
                active.priority = priority
            return active

    now = datetime.utcnow()
    job = Job(
        type=type,
        status=JobStatus.PENDING.value,
        priority=priority,
        target_type=target_type,
        target_id=target_id,
        payload=json.dumps(payload, ensure_ascii=False) if payload is not None else None,
        user_id=user_id,
        subject_id=subject_id,
        locale=locale,
        idempotency_key=idempotency_key,
        max_attempts=max_attempts,
        run_after=run_after,
        attempts=0,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    await db.flush()
    return job


async def requeue(db: AsyncSession, job: Job, *, priority: Optional[int] = None) -> None:
    """把一条已结束(失败/取消/暂停/成功)的 job 放回队尾重新执行。

    计数、错误、暂停原因、服务商与进度全部清空;排队时间改为现在,所以排在队尾。
    """
    now = datetime.utcnow()
    job.status = JobStatus.PENDING.value
    job.attempts = 0
    job.error = None
    job.paused_reason = None
    job.provider_id = None
    job.progress = None
    job.run_after = None
    job.started_at = None
    job.finished_at = None
    job.created_at = now
    job.updated_at = now
    if priority is not None:
        job.priority = priority
    await db.flush()
    await _project(
        db,
        [(job.id, job.type, job.target_id)],
        JobStatus.PENDING,
        error=None,
        paused_reason=None,
        provider_id=None,
        progress=None,
    )

# endregion


# region 查询

def payload_of(job: Job) -> Dict[str, Any]:
    """解析 job 的 payload;为空或损坏时返回空字典。"""
    if not job.payload:
        return {}
    try:
        value = json.loads(job.payload)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


async def latest_for_target(
    db: AsyncSession, target_type: str, target_id: int, *, type: Optional[str] = None
) -> Optional[Job]:
    """某条业务记录最近的一条 job(不论状态)。"""
    stmt = select(Job).where(Job.target_type == target_type, Job.target_id == target_id)
    if type is not None:
        stmt = stmt.where(Job.type == type)
    return await db.scalar(stmt.order_by(Job.id.desc()).limit(1))


async def jobs_for_targets(
    db: AsyncSession, target_type: str, target_ids: Iterable[int], *, type: Optional[str] = None
) -> Dict[int, Job]:
    """一批业务记录各自最近的 job:{target_id: job}。"""
    ids = list(set(target_ids))
    found: Dict[int, Job] = {}
    for chunk in _chunks(ids):
        stmt = select(Job).where(Job.target_type == target_type, Job.target_id.in_(chunk))
        if type is not None:
            stmt = stmt.where(Job.type == type)
        for job in (await db.execute(stmt.order_by(Job.id))).scalars().all():
            # 按 id 升序遍历,后写入的覆盖先写入的,得到每条记录最新的 job。
            found[job.target_id] = job
    return found


async def queue_positions(db: AsyncSession, job_ids: Iterable[int]) -> Dict[int, int]:
    """排队中的 job 前面还有几个 job(含正在执行的)。worker 串行执行,所以这就是等待数。

    顺序与 worker 领取顺序一致:先算执行中的,再按优先级高→低、排队时间早→晚。
    """
    wanted = set(job_ids)
    if not wanted:
        return {}
    rows = (
        await db.execute(
            select(Job.id, Job.status)
            .where(
                Job.status.in_([JobStatus.PENDING.value, JobStatus.RUNNING.value]),
                Job.type.in_(registered_types()),
            )
            .order_by(
                # 执行中的排在最前(running > pending 按字母序不成立,所以显式比较)。
                (Job.status == JobStatus.RUNNING.value).desc(),
                Job.priority.desc(),
                Job.created_at,
                Job.id,
            )
        )
    ).all()
    positions: Dict[int, int] = {}
    ahead = 0
    for job_id, status in rows:
        if status == JobStatus.PENDING.value and job_id in wanted:
            positions[job_id] = ahead
        ahead += 1
    return positions

# endregion


# region worker:领取与执行中的状态变化

async def claim_next(db: AsyncSession, *, use_row_lock: bool, now: Optional[datetime] = None) -> Optional[Job]:
    """领取下一条可执行的 job,标记为执行中并提交。没有可执行的 job 时返回 None(不提交)。

    :param use_row_lock: MySQL 下用 ``FOR UPDATE SKIP LOCKED`` 让多个 worker 并发领取
        互不冲突;SQLite(桌面版)只有一个 worker,不需要行锁。
    """
    now = now or datetime.utcnow()
    stmt = (
        select(Job)
        .where(
            Job.status == JobStatus.PENDING.value,
            Job.type.in_(registered_types()),
            or_(Job.run_after.is_(None), Job.run_after <= now),
        )
        .order_by(Job.priority.desc(), Job.created_at, Job.id)
        .limit(1)
    )
    if use_row_lock:
        stmt = stmt.with_for_update(skip_locked=True)
    job = await db.scalar(stmt)
    if job is None:
        return None
    await claim(db, job, now=now)
    return job


async def claim(db: AsyncSession, job: Job, *, now: Optional[datetime] = None) -> None:
    """把一条指定的待执行 job 标记为执行中并提交(``claim_next`` 选中后调用;测试也用它直接执行某条 job)。"""
    now = now or datetime.utcnow()
    job.status = JobStatus.RUNNING.value
    job.attempts = (job.attempts or 0) + 1
    job.started_at = now
    job.finished_at = None
    job.updated_at = now
    job.error = None
    job.paused_reason = None
    job.progress = None
    await db.flush()
    await _project(
        db, [(job.id, job.type, job.target_id)], JobStatus.RUNNING,
        error=None, paused_reason=None, progress=None,
    )
    await db.commit()


async def update_running(db: AsyncSession, job_id: int, **values: Any) -> bool:
    """只在 job 仍处于执行中时更新它(例如写入进度);返回是否写入成功。不提交。

    返回 False 说明 job 已被取消、删除或重置,调用方应停止执行。
    ``progress`` 若一并给出,会同步投影到业务表。
    """
    row = await _running_row(db, job_id)
    if row is None:
        return False
    values["updated_at"] = datetime.utcnow()
    result = await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING.value)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if not result.rowcount:
        return False
    projected = {k: v for k, v in values.items() if k in ("progress", "provider_id", "error")}
    if projected:
        await _project(db, [row], JobStatus.RUNNING, **projected)
    return True


async def finish(
    db: AsyncSession,
    job_id: int,
    status: JobStatus,
    *,
    error: Optional[str] = None,
    progress: Optional[str] = None,
    provider_id: Optional[int] = None,
) -> bool:
    """把执行中的 job 结束为成功或失败;返回是否写入成功。不提交。

    成功时业务结果由处理器自己写进业务表,这里只同步「失败」的投影。
    """
    if status not in (JobStatus.SUCCEEDED, JobStatus.FAILED):
        raise ValueError(f"finish() only accepts succeeded/failed, got {status}")
    row = await _running_row(db, job_id)
    if row is None:
        return False
    now = datetime.utcnow()
    values: Dict[str, Any] = dict(status=status.value, updated_at=now, finished_at=now, error=error)
    if progress is not None:
        values["progress"] = progress
    if provider_id is not None:
        values["provider_id"] = provider_id
    result = await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING.value)
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if not result.rowcount:
        return False
    if status == JobStatus.FAILED:
        await _project(db, [row], JobStatus.FAILED, error=error, progress=progress)
    return True


async def pause_for_provider(
    db: AsyncSession,
    *,
    job_id: int,
    reason: ImportPauseReason,
    provider_id: Optional[int],
    message: Optional[str] = None,
) -> int:
    """AI 服务商出错:暂停当前 job,以及排队中、同样会用到该服务商的其他 job。

    返回被暂停的数量。不提交。不同任务类型(导入、拆解……)一视同仁:服务商坏了,
    所有要用它的 job 一起停,恢复时也一起恢复。
    """
    paused = await _transition(
        db,
        [Job.id == job_id, Job.status == JobStatus.RUNNING.value],
        JobStatus.PAUSED,
        values=dict(paused_reason=reason.value, provider_id=provider_id, error=message, progress=None),
    )
    sibling_ids = await _pending_ids_on_provider(db, provider_id, exclude_id=job_id)
    for chunk in _chunks(sibling_ids):
        paused += await _transition(
            db,
            [Job.id.in_(chunk), Job.status == JobStatus.PENDING.value],
            JobStatus.PAUSED,
            values=dict(paused_reason=reason.value, provider_id=provider_id, error=None),
        )
    return paused


async def requeue_running(
    db: AsyncSession, *, user_id: Optional[int] = None, types: Optional[Sequence[str]] = None
) -> int:
    """把执行中的 job 放回队列(进程重启后的中断任务、用户手动「重置卡住的任务」)。不提交。"""
    conditions: List[ColumnElement[bool]] = [Job.status == JobStatus.RUNNING.value]
    if user_id is not None:
        conditions.append(Job.user_id == user_id)
    if types is not None:
        conditions.append(Job.type.in_(list(types)))
    return await _transition(
        db, conditions, JobStatus.PENDING, values=dict(progress=None, error=None, started_at=None)
    )

# endregion


# region 恢复暂停的 job

async def resume_targets(
    db: AsyncSession,
    target_type: str,
    target_ids: Sequence[int],
    *,
    owner_id: Optional[int] = None,
) -> int:
    """恢复指定业务记录的暂停 job。``owner_id`` 不为空时只恢复该用户发起的。不提交。"""
    if not target_ids:
        return 0
    conditions: List[ColumnElement[bool]] = [
        Job.target_type == target_type,
        Job.target_id.in_(list(target_ids)),
    ]
    if owner_id is not None:
        conditions.append(Job.user_id == owner_id)
    return await _resume_where(db, *conditions)


async def resume_all(
    db: AsyncSession, *, types: Optional[Sequence[str]] = None, owner_id: Optional[int] = None
) -> int:
    """恢复全部暂停的 job(可按类型、发起人过滤)。不提交。"""
    conditions: List[ColumnElement[bool]] = []
    if types is not None:
        conditions.append(Job.type.in_(list(types)))
    if owner_id is not None:
        conditions.append(Job.user_id == owner_id)
    return await _resume_where(db, *conditions)


async def resume_provider(db: AsyncSession, provider_id: Optional[int]) -> int:
    """服务商又能成功调用了:恢复因它暂停的全部 job。不提交。"""
    if provider_id is None:
        return 0
    return await _resume_where(db, Job.provider_id == provider_id)


async def resume_after_ai_config_change(db: AsyncSession) -> int:
    """AI 设置改动后,把因 Key / 模型问题暂停的 job 放回队列;仍不可用会再次暂停。不提交。"""
    return await _resume_where(
        db,
        Job.paused_reason.in_([ImportPauseReason.AUTH.value, ImportPauseReason.MODEL.value]),
    )


async def resume_stale_unavailable(db: AsyncSession, *, now: Optional[datetime] = None) -> int:
    """「服务不可达」而暂停超过一段时间的 job 放回队列试探一次。不提交。"""
    cutoff = (now or datetime.utcnow()) - UNAVAILABLE_RETRY_AFTER
    return await _resume_where(
        db,
        Job.paused_reason == ImportPauseReason.UNAVAILABLE.value,
        Job.updated_at < cutoff,
    )

# endregion


# region 取消与删除

async def cancel(db: AsyncSession, job: Job) -> bool:
    """取消一条未结束的 job;正在执行的会在几秒内被 runner 中止。返回是否取消成功。不提交。"""
    return bool(
        await _transition(
            db,
            [Job.id == job.id, Job.status.in_(ACTIVE_JOB_STATUSES)],
            JobStatus.CANCELLED,
            values=dict(paused_reason=None, progress=None, finished_at=datetime.utcnow()),
        )
    )


async def cancel_for_targets(
    db: AsyncSession, target_type: str, target_ids: Sequence[int], *, type: Optional[str] = None
) -> int:
    """取消一批业务记录上未结束的 job。不提交。"""
    cancelled = 0
    for chunk in _chunks(list(target_ids)):
        conditions: List[ColumnElement[bool]] = [
            Job.target_type == target_type,
            Job.target_id.in_(chunk),
            Job.status.in_(ACTIVE_JOB_STATUSES),
        ]
        if type is not None:
            conditions.append(Job.type == type)
        cancelled += await _transition(
            db, conditions, JobStatus.CANCELLED,
            values=dict(paused_reason=None, progress=None, finished_at=datetime.utcnow()),
        )
    return cancelled


async def delete_for_target(db: AsyncSession, target_type: str, target_id: int) -> int:
    """业务记录被删除时,删掉它的全部 job;正在执行的会因 job 消失而被 runner 中止。不提交。"""
    result = await db.execute(
        delete(Job)
        .where(Job.target_type == target_type, Job.target_id == target_id)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0

# endregion


# region 内部实现

def _chunks(ids: Sequence[int]) -> Iterable[List[int]]:
    """把 id 列表切成不超过 ``_CHUNK`` 的小段。"""
    ids = list(ids)
    for start in range(0, len(ids), _CHUNK):
        yield ids[start:start + _CHUNK]


async def _running_row(db: AsyncSession, job_id: int) -> Optional[_JobRow]:
    """执行中的 job 的 (id, type, target_id);不在执行中则返回 None。"""
    row = (
        await db.execute(
            select(Job.id, Job.type, Job.target_id).where(
                Job.id == job_id, Job.status == JobStatus.RUNNING.value
            )
        )
    ).first()
    return (row[0], row[1], row[2]) if row else None


async def _transition(
    db: AsyncSession,
    conditions: Sequence[ColumnElement[bool]],
    status: JobStatus,
    *,
    values: Dict[str, Any],
) -> int:
    """把满足条件的 job 改为 ``status``,并把变化投影到业务表;返回受影响的数量。

    先带行锁查出受影响的 job,再按 id 更新。MySQL 下行锁保证查出来的就是改掉的;
    SQLite 不渲染 FOR UPDATE,但它只有一个写者,同样不会出现中途被别人改掉的情况。
    """
    rows: List[_JobRow] = [
        (r[0], r[1], r[2])
        for r in (
            await db.execute(select(Job.id, Job.type, Job.target_id).where(*conditions).with_for_update())
        ).all()
    ]
    if not rows:
        return 0
    now = datetime.utcnow()
    for chunk in _chunks([r[0] for r in rows]):
        await db.execute(
            update(Job)
            .where(Job.id.in_(chunk))
            .values(status=status.value, updated_at=now, **values)
            .execution_options(synchronize_session=False)
        )
    projected = {
        k: v for k, v in values.items() if k in ("error", "paused_reason", "provider_id", "progress")
    }
    await _project(db, rows, status, **projected)
    return len(rows)


async def _resume_where(db: AsyncSession, *conditions: ColumnElement[bool]) -> int:
    """暂停 → 待执行。"""
    return await _transition(
        db,
        [Job.status == JobStatus.PAUSED.value, *conditions],
        JobStatus.PENDING,
        values=dict(paused_reason=None, error=None, progress=None),
    )


async def _project(db: AsyncSession, rows: Sequence[_JobRow], status: JobStatus, **values: Any) -> None:
    """按任务类型分组,调用各处理器把状态同步到业务表。"""
    by_type: Dict[str, List[int]] = defaultdict(list)
    for _job_id, job_type, target_id in rows:
        if target_id is not None:
            by_type[job_type].append(target_id)
    for job_type, target_ids in by_type.items():
        handler = get_handler(job_type)
        if handler is None:
            continue
        for chunk in _chunks(target_ids):
            await handler.project(db, chunk, status, **values)


async def _pending_ids_on_provider(
    db: AsyncSession, provider_id: Optional[int], *, exclude_id: Optional[int] = None
) -> List[int]:
    """排队中、需要 AI、且(按发起人的模型设置)会落在同一服务商上的 job。"""
    from app.services.ai_resolver import resolve_provider_id

    stmt = select(Job).where(Job.status == JobStatus.PENDING.value)
    if exclude_id is not None:
        stmt = stmt.where(Job.id != exclude_id)
    ids: List[int] = []
    # 同一发起人、同一用途解析出的服务商相同,缓存起来避免成千上万次重复解析。
    cache: Dict[tuple, Optional[int]] = {}
    for job in (await db.execute(stmt)).scalars().all():
        handler = get_handler(job.type)
        if handler is None:
            continue
        purpose = await handler.ai_purpose(db, job)
        if purpose is None:
            continue
        key = (job.user_id, purpose)
        if key not in cache:
            cache[key] = await resolve_provider_id(db, user_id=job.user_id, purpose=purpose)  # type: ignore[arg-type]
        if cache[key] == provider_id:
            ids.append(job.id)
    return ids

# endregion
