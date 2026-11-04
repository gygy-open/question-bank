"""导入队列:所有导入后台识别 → 待审核 → 审核入库;AI 出错按类别暂停/失败并自动恢复。"""
import asyncio
import io
import zipfile
from datetime import datetime, timedelta

import httpx
import openai
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import worker
from app.core import storage
from app.core.config import settings
from app.core.permissions import SubjectRole
from app.core.secrets import encrypt_secret
from app.core.security import create_access_token
from app.models.ai_config import AIModel, AIProvider, UserAIPreference
from app.models.import_task import ImportPauseReason, ImportTask, ImportTaskStatus
from app.models.media_asset import MediaAsset
from app.models.question import Question
from app.models.subject import Subject
from app.models.system_setting import SystemSetting
from app.models.user import User
from app.models.job import Job
from app.services import import_task_service as tasks_svc
from app.services.importing.job import enqueue_import
from app.services.jobs import job_service
from app.services.ai_errors import classify_ai_error, with_ai_retry
from app.services.ai_provider import ResponseTruncatedError
from app.services.doc_processor import doc_processor
from app.services.importing.contracts import ExtractionResult
from app.services.media_gc import _referenced_hashes

API = "/api/v1"
TAGGED = "【题目】1+1=?\n【答案】2\n【题目】2+2=?\n【答案】4\n"
PLAIN = "1. 1+1=?\n2. 2+2=?\n"


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    return buf.getvalue()


def _zip(members: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _response(status: int, body: dict | None = None, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body or {}, headers=headers, request=httpx.Request("POST", "https://ai.test"))


def _openai_error(cls, status: int, body: dict | None = None):
    return cls("boom", response=_response(status, body), body=body)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    (tmp_path / "static").mkdir()
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
async def people(db_session, grant_role):
    alice = User(username="q_alice", full_name="Alice", hashed_password="x", is_active=True)
    bob = User(username="q_bob", full_name="Bob", hashed_password="x", is_active=True)
    subject = Subject(name="数学", slug="math-import-queue")
    db_session.add_all([alice, bob, subject])
    await db_session.commit()
    for user in (alice, bob):
        await grant_role(user, subject, SubjectRole.EDITOR)
        user.last_active_subject_id = subject.id
    await db_session.commit()
    return {"alice": alice, "bob": bob, "subject": subject}


@pytest.fixture
async def global_model(db_session):
    provider = AIProvider(name="global", interface_type="openai", api_key=encrypt_secret("sk-global"))
    model = AIModel(provider=provider, name="g-chat", is_vision_capable=True)
    db_session.add_all([provider, model])
    await db_session.flush()
    db_session.add_all([
        SystemSetting(key="AI_TEXT_MODEL_ID", value=str(model.id)),
        SystemSetting(key="AI_VISION_MODEL_ID", value=str(model.id)),
    ])
    await db_session.commit()
    return model


class FakeExtractor:
    """替换 AI/标签抽取:按脚本返回结果或抛错,并记录阶段回调。"""

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls = []
        self.stages = []
        self.gate: asyncio.Event | None = None

    async def extract(self, content, db, *, on_stage=None, **kwargs):
        self.calls.append(content)
        if on_stage:
            await on_stage("extracting")
            self.stages.append("extracting")
        if self.gate is not None:
            await self.gate.wait()
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome or ExtractionResult(
            questions=[{"id": "t1", "content": "1+1=?", "answer": "2", "type": "free_response"}]
        )


@pytest.fixture
def fake_ai(monkeypatch):
    fake = FakeExtractor()
    real = doc_processor._extractor_for

    def pick(method):
        return real(method) if method == "structured" else fake

    monkeypatch.setattr(doc_processor, "_extractor_for", pick)
    return fake


async def _task(db, user, *, content=PLAIN.encode(), file_type="markdown", method="auto", status=ImportTaskStatus.PENDING, **extra) -> ImportTask:
    sha = storage.put_bytes(content)
    task = ImportTask(
        user_id=user.id,
        subject_id=user.last_active_subject_id,
        file_path="virtual",
        source_sha256=sha,
        content_sha256=sha,
        original_filename=extra.pop("filename", f"paper-{file_type}"),
        file_type=file_type,
        status=status,
        source=tasks_svc.SOURCE_IMPORT,
        method=method,
        mode="extract",
        **extra,
    )
    db.add(task)
    await db.flush()
    # 与 API 创建导入时一样:每条排队 / 暂停的导入任务都有一个执行 job,状态与任务一致。
    if status in (ImportTaskStatus.PENDING, ImportTaskStatus.PAUSED):
        job = await enqueue_import(db, task)
        if status == ImportTaskStatus.PAUSED:
            job.status = "paused"
            job.paused_reason = task.paused_reason
            job.provider_id = task.provider_id
    await db.commit()
    return task


async def _claim(db, task) -> Job:
    """领取这条导入任务的 job(标记为执行中),模拟 worker 选中它。"""
    job = await job_service.latest_for_target(db, tasks_svc.JOB_TARGET_TYPE, task.id)
    await job_service.claim(db, job)
    return job


async def _run(db, task, **kwargs):
    kwargs.setdefault("cancel_poll_seconds", None)
    await worker.process_job(db, await _claim(db, task), **kwargs)
    await db.refresh(task)
    return task


# --------------------------------------------------------------------------- #
# AI 错误分类与重试
# --------------------------------------------------------------------------- #
def test_classify_openai_errors():
    assert classify_ai_error(_openai_error(openai.AuthenticationError, 401)).reason is ImportPauseReason.AUTH
    quota = _openai_error(openai.RateLimitError, 429, {"error": {"code": "insufficient_quota"}})
    assert (classify_ai_error(quota).category, classify_ai_error(quota).reason) == ("provider", ImportPauseReason.QUOTA)
    limited = classify_ai_error(_openai_error(openai.RateLimitError, 429))
    assert limited.category == "transient"
    assert classify_ai_error(_openai_error(openai.APIStatusError, 402)).reason is ImportPauseReason.QUOTA
    assert classify_ai_error(_openai_error(openai.NotFoundError, 404)).reason is ImportPauseReason.MODEL
    assert classify_ai_error(_openai_error(openai.InternalServerError, 503)).category == "transient"
    assert classify_ai_error(_openai_error(openai.BadRequestError, 400)).category == "document"
    timeout = openai.APITimeoutError(request=httpx.Request("POST", "https://ai.test"))
    assert classify_ai_error(timeout).category == "transient"


def test_classify_gemini_and_other_errors():
    from google.genai import errors as genai_errors

    bad_key = genai_errors.ClientError(400, {"error": {"message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}})
    assert classify_ai_error(bad_key).reason is ImportPauseReason.AUTH
    exhausted = genai_errors.ClientError(429, {"error": {"message": "Resource exhausted", "status": "RESOURCE_EXHAUSTED"}})
    assert classify_ai_error(exhausted).category == "transient"
    assert classify_ai_error(genai_errors.ServerError(503, {"error": {"message": "overloaded"}})).category == "transient"
    assert classify_ai_error(ResponseTruncatedError("cut")).category == "document"
    assert classify_ai_error(ValueError("bad json")).category == "document"
    assert classify_ai_error(httpx.ConnectError("down")).category == "transient"
    assert classify_ai_error(RuntimeError("???")).category == "unknown"


async def test_retry_only_transient_errors():
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    attempts = []

    async def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise _openai_error(openai.InternalServerError, 503)
        return "ok"

    assert await with_ai_retry(flaky, sleep=fake_sleep) == "ok"
    assert len(attempts) == 3 and len(sleeps) == 2

    async def bad_key():
        attempts.append(1)
        raise _openai_error(openai.AuthenticationError, 401)

    attempts.clear()
    with pytest.raises(openai.AuthenticationError):
        await with_ai_retry(bad_key, sleep=fake_sleep)
    assert len(attempts) == 1


# --------------------------------------------------------------------------- #
# 创建任务
# --------------------------------------------------------------------------- #
async def test_upload_creates_one_task_per_supported_file(client, people, db_session):
    files = [
        ("files", ("a.docx", b"PK-docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("files", ("b.md", TAGGED.encode(), "text/markdown")),
        ("files", ("c.zip", _zip({"q.md": b"x"}), "application/zip")),
        ("files", ("d.png", _png(), "image/png")),
        ("files", ("e.exe", b"MZ", "application/octet-stream")),
        ("files", ("broken.zip", b"not a zip", "application/zip")),
    ]
    response = await client.post(f"{API}/imports?method=structured", files=files, headers=_auth(people["alice"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skipped"] == ["e.exe", "broken.zip"]
    by_name = {item["original_filename"]: item for item in body["items"]}
    assert {name: item["file_type"] for name, item in by_name.items()} == {
        "a.docx": "docx", "b.md": "markdown", "c.zip": "archive", "d.png": "image",
    }
    assert by_name["b.md"]["method"] == "structured"
    assert by_name["d.png"]["method"] == "ai"
    assert all(item["status"] == "pending" and not item["auto_commit"] for item in body["items"])
    assert [by_name[n]["queue_ahead"] for n in ("a.docx", "b.md", "c.zip", "d.png")] == [0, 1, 2, 3]


async def test_text_import_uses_first_line_as_name(client, people, db_session):
    response = await client.post(
        f"{API}/imports/text",
        json={"content": "\n# 期中测验\n【题目】1+1=?"},
        headers=_auth(people["alice"]),
    )
    assert response.status_code == 200, response.text
    task = await db_session.get(ImportTask, response.json()["id"])
    assert task.original_filename == "期中测验" and task.file_type == "text" and task.method == "auto"
    assert storage.read_bytes(task.source_sha256).decode() == "# 期中测验\n【题目】1+1=?"

    tagged = await client.post(f"{API}/imports/text", json={"content": TAGGED}, headers=_auth(people["alice"]))
    assert tagged.json()["original_filename"] == "1+1=?"

    empty = await client.post(f"{API}/imports/text", json={"content": "  "}, headers=_auth(people["alice"]))
    assert empty.status_code == 400 and empty.json()["code"] == "import_task.empty_text"


async def test_upload_requires_edit_permission_on_subject(client, people, db_session):
    other = Subject(name="物理", slug="physics-import-queue")
    db_session.add(other)
    await db_session.commit()
    response = await client.post(
        f"{API}/imports?subject_id={other.id}",
        files=[("files", ("a.md", b"x", "text/markdown"))],
        headers=_auth(people["alice"]),
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# 识别 → 待审核 → 入库
# --------------------------------------------------------------------------- #
async def test_auto_method_uses_tags_and_stops_for_review(client, db_session, people, fake_ai):
    task = await _task(db_session, people["alice"], content=TAGGED.encode())
    await _run(db_session, task)

    assert task.status == ImportTaskStatus.REVIEW_READY
    assert fake_ai.calls == []  # 有标签,不调用 AI
    assert tasks_svc.progress_of(task) == {"stage": "ready", "method": "structured", "count": 2}
    response = await client.get(f"{API}/imports/{task.id}/result", headers=_auth(people["alice"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["questions"]) == 2 and body["method"] == "structured"
    assert body["duplicate_of"] is None and body["task"]["status"] == "review_ready"
    assert task.result_sha256 in await _referenced_hashes(db_session)

    stranger = await client.get(f"{API}/imports/{task.id}/result", headers=_auth(people["bob"]))
    assert stranger.status_code == 403


async def test_auto_method_without_tags_uses_ai_and_reports_stages(db_session, people, global_model, fake_ai):
    task = await _task(db_session, people["alice"])
    await _run(db_session, task)

    assert task.status == ImportTaskStatus.REVIEW_READY
    assert fake_ai.calls == [PLAIN] and fake_ai.stages == ["extracting"]
    assert task.provider_id == global_model.provider_id
    assert tasks_svc.load_result(task)["method"] == "ai"


async def test_archive_images_become_assets_before_parsing(db_session, people):
    archive = _zip({"q.md": "【题目】看图 ![图](p.png)\n【答案】A\n".encode(), "p.png": _png()})
    task = await _task(db_session, people["alice"], content=archive, file_type="archive", method="structured")
    await _run(db_session, task)

    assert task.status == ImportTaskStatus.REVIEW_READY
    asset = (await db_session.execute(select(MediaAsset))).scalars().one()
    assert asset.subject_id == people["subject"].id
    assert f"/api/v1/media/{asset.id}/content" in str(tasks_svc.load_result(task)["questions"])


async def test_empty_result_fails_with_reason(db_session, people):
    task = await _task(db_session, people["alice"], content="no tags here".encode(), method="structured")
    await _run(db_session, task)
    assert task.status == ImportTaskStatus.FAILED
    assert tasks_svc.progress_of(task)["error_code"] == tasks_svc.ERROR_NO_QUESTIONS


async def test_commit_review_completes_the_same_task(client, db_session, people):
    task = await _task(db_session, people["alice"], content=TAGGED.encode())
    await _run(db_session, task)
    result = (await client.get(f"{API}/imports/{task.id}/result", headers=_auth(people["alice"]))).json()
    question = result["questions"][0]
    body = {
        "scope": "personal",
        "questions": [{**question, "subject_id": people["subject"].id, "status": "draft"}],
        "outline": [],
        "import_task_id": task.id,
        "idempotency_key": "key-1",
    }
    url = f"{API}/subjects/{people['subject'].id}/paper-imports"

    response = await client.post(url, json=body, headers=_auth(people["alice"]))
    assert response.status_code == 200, response.text
    assert response.json()["import_task_id"] == task.id
    await db_session.refresh(task)
    assert task.status == ImportTaskStatus.COMPLETED and task.result_sha256 is None
    assert (await db_session.execute(select(ImportTask))).scalars().all() == [task]
    assert (await db_session.execute(select(Question))).scalars().one().import_task_id == task.id

    replay = await client.post(url, json=body, headers=_auth(people["alice"]))
    assert replay.status_code == 200 and replay.json()["reused_existing"]
    again = await client.post(url, json={**body, "idempotency_key": "key-2"}, headers=_auth(people["alice"]))
    assert again.status_code == 409 and again.json()["code"] == "import_task.not_reviewable"
    stranger = await client.post(url, json=body, headers=_auth(people["bob"]))
    assert stranger.status_code == 404


async def test_auto_commit_saves_questions_without_review(db_session, people):
    task = await _task(db_session, people["alice"], content=TAGGED.encode(), auto_commit=True)
    await _run(db_session, task)
    assert task.status == ImportTaskStatus.COMPLETED
    assert task.result_sha256 is None
    assert len((await db_session.execute(select(Question))).scalars().all()) == 2


# --------------------------------------------------------------------------- #
# 取消
# --------------------------------------------------------------------------- #
async def test_cancel_stops_a_running_task(client, engine, db_session, people, global_model, fake_ai):
    fake_ai.gate = asyncio.Event()
    task = await _task(db_session, people["alice"])
    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    run = asyncio.create_task(
        worker.process_job(db_session, await _claim(db_session, task), session_factory=maker, cancel_poll_seconds=0.02)
    )
    while not fake_ai.stages:
        await asyncio.sleep(0.01)
    response = await client.post(f"{API}/imports/{task.id}/cancel", headers=_auth(people["alice"]))
    assert response.status_code == 200
    await asyncio.wait_for(run, timeout=5)

    await db_session.refresh(task)
    assert task.status == ImportTaskStatus.CANCELLED and task.result_sha256 is None


async def test_cancel_discards_review_result(client, db_session, people):
    task = await _task(db_session, people["alice"], content=TAGGED.encode())
    await _run(db_session, task)
    response = await client.post(f"{API}/imports/{task.id}/cancel", headers=_auth(people["alice"]))
    assert response.status_code == 200
    await db_session.refresh(task)
    assert task.status == ImportTaskStatus.CANCELLED and task.result_sha256 is None


# --------------------------------------------------------------------------- #
# AI 出错:暂停 / 失败 / 恢复
# --------------------------------------------------------------------------- #
async def test_missing_model_pauses_ai_tasks_only(db_session, people, fake_ai):
    task = await _task(db_session, people["alice"])
    ai_sibling = await _task(db_session, people["alice"], method="ai")
    image = await _task(db_session, people["bob"], content=_png(), file_type="image")
    tagged = await _task(db_session, people["alice"], content=TAGGED.encode(), method="structured")

    await _run(db_session, task)

    for t in (task, ai_sibling, image, tagged):
        await db_session.refresh(t)
    assert (task.status, task.paused_reason) == (ImportTaskStatus.PAUSED, "model")
    assert ai_sibling.status == ImportTaskStatus.PAUSED and image.status == ImportTaskStatus.PAUSED
    assert tagged.status == ImportTaskStatus.PENDING
    assert fake_ai.calls == []


async def test_provider_error_pauses_only_tasks_on_the_same_provider(db_session, people, global_model, fake_ai):
    personal = AIProvider(name="bob-own", interface_type="openai", api_key=encrypt_secret("sk-bob"), owner_id=people["bob"].id)
    bob_model = AIModel(provider=personal, name="bob-chat")
    db_session.add_all([personal, bob_model])
    await db_session.flush()
    db_session.add(UserAIPreference(user_id=people["bob"].id, text_model_id=bob_model.id))
    await db_session.commit()

    fake_ai.outcomes = [_openai_error(openai.AuthenticationError, 401)]
    task = await _task(db_session, people["alice"])
    alice_next = await _task(db_session, people["alice"])
    bob_task = await _task(db_session, people["bob"])

    await _run(db_session, task)

    for t in (task, alice_next, bob_task):
        await db_session.refresh(t)
    assert (task.status, task.paused_reason, task.provider_id) == (ImportTaskStatus.PAUSED, "auth", global_model.provider_id)
    assert task.error_message
    assert alice_next.status == ImportTaskStatus.PAUSED
    assert bob_task.status == ImportTaskStatus.PENDING


async def test_document_error_fails_only_that_task(db_session, people, global_model, fake_ai):
    fake_ai.outcomes = [ResponseTruncatedError("output truncated")]
    task = await _task(db_session, people["alice"])
    sibling = await _task(db_session, people["alice"])
    await _run(db_session, task)
    await db_session.refresh(sibling)
    assert task.status == ImportTaskStatus.FAILED
    assert tasks_svc.progress_of(task)["error_code"] == tasks_svc.ERROR_AI_DOCUMENT
    assert sibling.status == ImportTaskStatus.PENDING


async def test_repeated_unknown_errors_trip_the_breaker(db_session, people, global_model, fake_ai):
    fake_ai.outcomes = [RuntimeError("weird")] * 3
    breaker = worker.ProviderBreaker()
    tasks = [await _task(db_session, people["alice"]) for _ in range(4)]
    for t in tasks[:3]:
        await _run(db_session, t, breaker=breaker)
    await db_session.refresh(tasks[3])
    assert [t.status for t in tasks[:2]] == [ImportTaskStatus.FAILED] * 2
    assert (tasks[2].status, tasks[2].paused_reason) == (ImportTaskStatus.PAUSED, "unavailable")
    assert tasks[3].status == ImportTaskStatus.PAUSED


async def test_success_resumes_tasks_paused_on_that_provider(db_session, people, global_model, fake_ai):
    paused = await _task(
        db_session, people["alice"], status=ImportTaskStatus.PAUSED,
        paused_reason="quota", provider_id=global_model.provider_id,
    )
    task = await _task(db_session, people["alice"])
    await _run(db_session, task)
    await db_session.refresh(paused)
    assert task.status == ImportTaskStatus.REVIEW_READY
    assert paused.status == ImportTaskStatus.PENDING and paused.paused_reason is None


async def test_unreachable_provider_is_retried_after_a_while(db_session, people):
    task = await _task(db_session, people["alice"], status=ImportTaskStatus.PAUSED, paused_reason="unavailable")
    assert await tasks_svc.resume_stale_unavailable(db_session) == 0
    assert await tasks_svc.resume_stale_unavailable(db_session, now=datetime.utcnow() + timedelta(minutes=6)) == 1
    await db_session.commit()
    await db_session.refresh(task)
    assert task.status == ImportTaskStatus.PENDING


async def test_ai_config_change_resumes_auth_and_model_pauses(client, db_session, people):
    admin = User(username="q_admin", hashed_password="x", is_active=True, is_superuser=True)
    db_session.add(admin)
    await db_session.commit()
    auth = await _task(db_session, people["alice"], status=ImportTaskStatus.PAUSED, paused_reason="auth")
    quota = await _task(db_session, people["alice"], status=ImportTaskStatus.PAUSED, paused_reason="quota")

    response = await client.post(
        f"{API}/ai-config/providers",
        json={"name": "fixed", "interface_type": "openai", "api_key": "sk-new", "models": [{"name": "m"}]},
        headers=_auth(admin),
    )
    assert response.status_code == 200, response.text
    await db_session.refresh(auth)
    await db_session.refresh(quota)
    assert auth.status == ImportTaskStatus.PENDING
    assert quota.status == ImportTaskStatus.PAUSED


async def test_resume_and_summary_endpoints(client, db_session, people):
    mine = await _task(db_session, people["alice"], status=ImportTaskStatus.PAUSED, paused_reason="quota")
    await _task(db_session, people["alice"], status=ImportTaskStatus.REVIEW_READY)
    theirs = await _task(db_session, people["bob"], status=ImportTaskStatus.PAUSED, paused_reason="quota")

    summary = (await client.get(f"{API}/imports/summary", headers=_auth(people["alice"]))).json()
    assert summary["counts"]["review_ready"] == 1 and summary["paused_reasons"] == {"quota": 1}

    response = await client.post(f"{API}/imports/resume", json={}, headers=_auth(people["alice"]))
    assert response.json() == {"count": 1}
    await db_session.refresh(mine)
    await db_session.refresh(theirs)
    assert mine.status == ImportTaskStatus.PENDING and theirs.status == ImportTaskStatus.PAUSED


async def test_list_shows_only_own_tasks_newest_first(client, db_session, people):
    first = await _task(db_session, people["alice"])
    second = await _task(db_session, people["alice"], status=ImportTaskStatus.REVIEW_READY)
    await _task(db_session, people["bob"])
    body = (await client.get(f"{API}/imports", headers=_auth(people["alice"]))).json()
    assert [item["id"] for item in body["items"]] == [second.id, first.id]
    filtered = (await client.get(f"{API}/imports?status=review_ready,paused", headers=_auth(people["alice"]))).json()
    assert [item["id"] for item in filtered["items"]] == [second.id]


# --------------------------------------------------------------------------- #
# 桌面通知
# --------------------------------------------------------------------------- #
async def test_desktop_notifier_reports_each_change_once(engine, db_session, people):
    from app.import_notifier import NotifierState, poll_once

    maker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    tr = lambda key, **params: f"{key}:{params}"  # noqa: E731
    state = NotifierState(since=datetime.utcnow() - timedelta(seconds=1))
    await _task(db_session, people["alice"], status=ImportTaskStatus.REVIEW_READY, filename="期中卷", progress='{"count": 3}')
    await _task(db_session, people["alice"], status=ImportTaskStatus.PAUSED, paused_reason="quota")
    await _task(db_session, people["alice"], status=ImportTaskStatus.PAUSED, paused_reason="quota")
    await _task(db_session, people["alice"], status=ImportTaskStatus.COMPLETED, filename="committed by user")

    messages = await poll_once(maker, state, tr)
    assert messages == [
        "notify.import_ready:{'name': '期中卷', 'count': 3}",
        "notify.imports_paused:{'count': 2}",
    ]
    assert await poll_once(maker, state, tr) == []
