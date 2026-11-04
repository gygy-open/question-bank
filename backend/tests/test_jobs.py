"""通用任务表 jobs:入队去重、领取顺序、跨类型按服务商暂停 / 恢复、runner 结果、存量导入补建 job。"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.core import storage
from app.core.config import settings
from app.core.secrets import encrypt_secret
from app.models.ai_config import AIModel, AIProvider
from app.models.import_task import ImportPauseReason, ImportTask, ImportTaskStatus
from app.models.job import Job, JobPriority, JobStatus
from app.models.subject import Subject
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.services import data_migrations
from app.services import import_task_service as tasks_svc
from app.services.jobs import JobContext, JobHandler, job_service, register_handler, run_job

# --------------------------------------------------------------------------- #
# 测试用处理器:按 payload 决定结果,记录被执行的 job。
# --------------------------------------------------------------------------- #
EXECUTED: list = []


@register_handler
class _ScriptedHandler(JobHandler):
    """payload.outcome: ok(默认,不显式结束) / fail / raise / pause。"""

    type = "test.scripted"

    async def run(self, ctx: JobContext) -> None:
        EXECUTED.append(ctx.job_id)
        outcome = ctx.payload.get("outcome", "ok")
        if outcome == "fail":
            await ctx.fail("scripted failure", error_code="scripted")
        elif outcome == "raise":
            raise RuntimeError("scripted crash")
        elif outcome == "pause":
            await ctx.pause(ImportPauseReason.QUOTA, ctx.payload.get("provider_id"), "quota exceeded")


@register_handler
class _OfflineHandler(JobHandler):
    """不需要 AI 的任务:服务商出故障时不应被一起暂停。"""

    type = "test.offline"

    async def ai_purpose(self, db, job):
        return None

    async def run(self, ctx: JobContext) -> None:
        EXECUTED.append(ctx.job_id)


@pytest.fixture(autouse=True)
def _reset_executed():
    EXECUTED.clear()
    yield
    EXECUTED.clear()


@pytest.fixture
async def provider(db_session):
    """全局文本模型落在这个服务商上:所有用户的文本类 job 都会用到它。"""
    p = AIProvider(name="global", interface_type="openai", api_key=encrypt_secret("sk-x"))
    model = AIModel(provider=p, name="chat")
    db_session.add_all([p, model])
    await db_session.flush()
    db_session.add(SystemSetting(key="AI_TEXT_MODEL_ID", value=str(model.id)))
    await db_session.commit()
    return p


async def _job(db, *, type="test.scripted", priority=JobPriority.USER, **kwargs) -> Job:
    job = await job_service.enqueue(db, type=type, priority=priority, **kwargs)
    await db.commit()
    return job


async def _claim_and_run(db, job: Job) -> Job:
    await job_service.claim(db, job)
    await run_job(db, job, cancel_poll_seconds=None)
    await db.refresh(job)
    return job


# --------------------------------------------------------------------------- #
# 入队
# --------------------------------------------------------------------------- #
async def test_enqueue_reuses_active_job_for_same_target_and_raises_priority(db_session):
    first = await _job(db_session, target_type="question", target_id=7, priority=JobPriority.BACKFILL)
    again = await _job(db_session, target_type="question", target_id=7, priority=JobPriority.USER)

    assert again.id == first.id
    assert again.priority == JobPriority.USER
    assert (await db_session.execute(select(Job))).scalars().all() == [first]


async def test_enqueue_creates_new_job_once_previous_finished(db_session):
    first = await _job(db_session, target_type="question", target_id=7)
    await _claim_and_run(db_session, first)
    second = await _job(db_session, target_type="question", target_id=7)

    assert first.status == JobStatus.SUCCEEDED.value
    assert second.id != first.id and second.status == JobStatus.PENDING.value


async def test_enqueue_is_idempotent_by_key(db_session):
    first = await _job(db_session, idempotency_key="k1")
    again = await _job(db_session, idempotency_key="k1")
    assert again.id == first.id


# --------------------------------------------------------------------------- #
# 领取顺序
# --------------------------------------------------------------------------- #
async def test_claim_order_is_priority_then_age_and_respects_run_after(db_session):
    backfill = await _job(db_session, priority=JobPriority.BACKFILL)
    auto = await _job(db_session, priority=JobPriority.AUTO)
    later = await _job(db_session, priority=JobPriority.USER, run_after=datetime.utcnow() + timedelta(hours=1))
    user = await _job(db_session, priority=JobPriority.USER)

    order = []
    while (job := await job_service.claim_next(db_session, use_row_lock=False)) is not None:
        order.append(job.id)
    assert order == [user.id, auto.id, backfill.id]
    await db_session.refresh(later)
    assert later.status == JobStatus.PENDING.value


async def test_unknown_job_types_are_not_claimed(db_session):
    db_session.add(Job(type="legacy.unknown", status="pending", priority=1000, attempts=0, max_attempts=1))
    await db_session.commit()
    assert await job_service.claim_next(db_session, use_row_lock=False) is None


async def test_queue_positions_count_running_and_higher_priority_jobs(db_session):
    running = await _job(db_session)
    await job_service.claim(db_session, running)
    low = await _job(db_session, priority=JobPriority.BACKFILL)
    high = await _job(db_session, priority=JobPriority.USER)

    positions = await job_service.queue_positions(db_session, [low.id, high.id, running.id])
    assert positions == {high.id: 1, low.id: 2}


# --------------------------------------------------------------------------- #
# runner
# --------------------------------------------------------------------------- #
async def test_runner_marks_success_when_handler_returns(db_session):
    job = await _claim_and_run(db_session, await _job(db_session))
    assert job.status == JobStatus.SUCCEEDED.value and job.attempts == 1 and job.finished_at
    assert EXECUTED == [job.id]


async def test_runner_records_explicit_failure_and_crashes(db_session):
    failed = await _claim_and_run(db_session, await _job(db_session, payload={"outcome": "fail"}))
    crashed = await _claim_and_run(db_session, await _job(db_session, payload={"outcome": "raise"}))

    assert failed.status == JobStatus.FAILED.value and failed.error == "scripted failure"
    assert '"error_code": "scripted"' in failed.progress
    assert crashed.status == JobStatus.FAILED.value and "scripted crash" in crashed.error


async def test_cancelled_job_cannot_be_marked_succeeded(db_session):
    job = await _job(db_session)
    await job_service.claim(db_session, job)
    await job_service.cancel(db_session, job)
    await db_session.commit()

    assert not await job_service.finish(db_session, job.id, JobStatus.SUCCEEDED)
    await db_session.refresh(job)
    assert job.status == JobStatus.CANCELLED.value


async def test_requeue_running_puts_interrupted_jobs_back(db_session):
    job = await _job(db_session)
    await job_service.claim(db_session, job)
    assert await job_service.requeue_running(db_session) == 1
    await db_session.commit()
    await db_session.refresh(job)
    assert job.status == JobStatus.PENDING.value


# --------------------------------------------------------------------------- #
# 按服务商暂停 / 恢复:不同任务类型一视同仁
# --------------------------------------------------------------------------- #
async def test_provider_pause_spans_job_types_and_skips_jobs_without_ai(db_session, provider):
    sibling = await _job(db_session)
    offline = await _job(db_session, type="test.offline")
    failing = await _job(db_session, payload={"outcome": "pause", "provider_id": provider.id})

    failing = await _claim_and_run(db_session, failing)
    for job in (sibling, offline):
        await db_session.refresh(job)

    assert (failing.status, failing.paused_reason, failing.provider_id) == ("paused", "quota", provider.id)
    assert failing.error == "quota exceeded"
    assert sibling.status == "paused" and sibling.error is None
    assert offline.status == "pending"

    assert await job_service.resume_provider(db_session, provider.id) == 2
    await db_session.commit()
    for job in (failing, sibling):
        await db_session.refresh(job)
        assert job.status == "pending" and job.paused_reason is None


async def test_stale_unavailable_pause_is_retried_later(db_session):
    job = await _job(db_session)
    job.status, job.paused_reason = "paused", ImportPauseReason.UNAVAILABLE.value
    await db_session.commit()

    assert await job_service.resume_stale_unavailable(db_session) == 0
    later = datetime.utcnow() + timedelta(minutes=6)
    assert await job_service.resume_stale_unavailable(db_session, now=later) == 1


# --------------------------------------------------------------------------- #
# 存量导入补建 job
# --------------------------------------------------------------------------- #
@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    (tmp_path / "static").mkdir()
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    return tmp_path


async def test_import_jobs_migration_backfills_in_flight_imports(db_session, data_dir):
    user = User(username="mig_u", hashed_password="x", is_active=True)
    subject = Subject(name="数学", slug="math-jobs-mig")
    db_session.add_all([user, subject])
    await db_session.commit()
    sha = storage.put_bytes(b"1+1=?")

    def task(status, **extra):
        return ImportTask(
            user_id=user.id, subject_id=subject.id, file_path="virtual", source_sha256=sha,
            original_filename=f"{status.value}.md", file_type="markdown", status=status,
            source=tasks_svc.SOURCE_IMPORT, method="auto", mode="extract", **extra,
        )

    pending = task(ImportTaskStatus.PENDING)
    processing = task(ImportTaskStatus.PROCESSING, progress='{"stage": "extracting"}')
    paused = task(ImportTaskStatus.PAUSED, paused_reason="auth", provider_id=3, error_message="bad key")
    done = task(ImportTaskStatus.REVIEW_READY)
    db_session.add_all([pending, processing, paused, done])
    await db_session.commit()

    assert await data_migrations._import_jobs(db_session) == "created 3 import jobs"
    assert await data_migrations._import_jobs(db_session) == "created 0 import jobs"

    jobs = await job_service.jobs_for_targets(
        db_session, tasks_svc.JOB_TARGET_TYPE, [pending.id, processing.id, paused.id, done.id]
    )
    assert set(jobs) == {pending.id, processing.id, paused.id}
    assert jobs[pending.id].status == "pending" and jobs[processing.id].status == "pending"
    assert (jobs[paused.id].status, jobs[paused.id].paused_reason, jobs[paused.id].provider_id) == ("paused", "auth", 3)
    await db_session.refresh(processing)
    assert processing.status == ImportTaskStatus.PENDING and processing.progress is None
