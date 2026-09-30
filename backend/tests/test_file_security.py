import io
import json

import pytest
from PIL import Image

from app.core.config import settings
from app.core.file_paths import sanitize_client_source_path
from app.core.permissions import SubjectRole
from app.core.security import create_access_token
from app.models.import_task import ImportTask, ImportTaskStatus
from app.models.question import Question, QuestionType
from app.models.subject import Subject
from app.models.user import User

API = "/api/v1"


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def data_dirs(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    media = tmp_path / "static" / "media"
    uploads.mkdir(parents=True)
    media.mkdir(parents=True)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(settings, "MEDIA_DIR", media)
    return {"root": tmp_path, "uploads": uploads, "media": media}


@pytest.fixture
async def people(db_session, grant_role):
    owner = User(username="src_owner", hashed_password="x", is_active=True)
    viewer = User(username="src_viewer", hashed_password="x", is_active=True)
    stranger = User(username="src_stranger", hashed_password="x", is_active=True)
    subject = Subject(name="历史", slug="history-src")
    db_session.add_all([owner, viewer, stranger, subject])
    await db_session.commit()
    await grant_role(owner, subject, SubjectRole.EDITOR)
    await grant_role(viewer, subject, SubjectRole.VIEWER)
    return {"owner": owner, "viewer": viewer, "stranger": stranger, "subject": subject}


async def _task_with_question(db_session, people, file_path: str) -> tuple[ImportTask, Question]:
    task = ImportTask(
        user_id=people["owner"].id,
        file_path=file_path,
        original_filename="试卷.md",
        file_type="markdown",
        status=ImportTaskStatus.COMPLETED,
    )
    db_session.add(task)
    await db_session.flush()
    question = Question(
        content=json.dumps({"type": "doc", "content": []}),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=people["subject"].id,
        created_by=people["owner"].id,
        import_task_id=task.id,
    )
    db_session.add(question)
    await db_session.commit()
    return task, question


async def test_upload_requires_login(client, data_dirs):
    response = await client.post(
        f"{API}/upload/docx", files={"file": ("a.docx", b"x", "application/octet-stream")}
    )
    assert response.status_code == 401


async def test_media_upload_rejects_svg_and_oversized(client, data_dirs, people, monkeypatch):
    from app.services import media_service

    url = f"{API}/subjects/{people['subject'].id}/media"
    headers = _auth(people["owner"])
    svg = await client.post(
        url,
        files={"file": ("x.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml")},
        headers=headers,
    )
    assert svg.status_code == 422

    monkeypatch.setattr(media_service, "MAX_IMAGE_BYTES", 16)
    response = await client.post(
        url, files={"file": ("a.png", _png_bytes(), "image/png")}, headers=headers
    )
    assert response.status_code == 413


def test_export_image_resolver_stays_inside_media_dir(data_dirs):
    from app.services.exporting.images import ImageResolver

    (data_dirs["root"] / "secret.txt").write_text("secret")
    (data_dirs["media"] / "ok.png").write_bytes(_png_bytes())
    resolver = ImageResolver()
    assert resolver.resolve("/static/media/../../secret.txt") is None
    assert resolver.resolve("/static/media/ok.png") == (data_dirs["media"] / "ok.png").resolve()


async def test_chat_image_reader_rejects_paths_outside_media(data_dirs, db_session):
    from app.api.v1.endpoints.chat import get_image_base64

    (data_dirs["root"] / "secret.png").write_bytes(_png_bytes())
    (data_dirs["media"] / "ok.png").write_bytes(_png_bytes())
    assert await get_image_base64(db_session, str(data_dirs["root"] / "secret.png")) is None
    assert await get_image_base64(db_session, "/static/media/../../secret.png") is None
    encoded = await get_image_base64(db_session, "/static/media/ok.png")
    assert encoded is not None and encoded.startswith("data:image/png;base64,")


def test_client_source_path_is_only_trusted_inside_uploads(data_dirs):
    inside = data_dirs["uploads"] / "s1" / "a.docx"
    inside.parent.mkdir()
    inside.write_bytes(b"x")
    outside = data_dirs["root"] / "config.json"
    outside.write_text("{}")
    assert sanitize_client_source_path(str(inside)) == str(inside.resolve())
    assert sanitize_client_source_path(str(outside)) == "virtual"
    assert sanitize_client_source_path(str(data_dirs["uploads"] / ".." / "config.json")) == "virtual"
    assert sanitize_client_source_path(None) == "virtual"


async def test_deleting_import_task_never_removes_files_outside_uploads(client, db_session, data_dirs, people):
    victim = data_dirs["root"] / "question_bank.db"
    victim.write_text("db")
    task, _ = await _task_with_question(db_session, people, str(victim))
    response = await client.delete(f"{API}/imports/{task.id}", headers=_auth(people["owner"]))
    assert response.status_code == 200, response.text
    assert victim.exists()


async def test_import_source_download_is_authorized(client, db_session, data_dirs, people):
    source = data_dirs["uploads"] / "s2" / "试卷.md"
    source.parent.mkdir()
    source.write_text("# 原卷", encoding="utf-8")
    task, question = await _task_with_question(db_session, people, str(source))
    url = f"{API}/imports/{task.id}/source"

    for user in (people["owner"], people["viewer"]):
        response = await client.get(url, headers=_auth(user))
        assert response.status_code == 200, response.text
        assert response.text == "# 原卷"
        assert response.headers["x-content-type-options"] == "nosniff"

    assert (await client.get(url, headers=_auth(people["stranger"]))).status_code == 404
    assert (await client.get(url)).status_code == 401

    detail = await client.get(f"{API}/questions/{question.id}", headers=_auth(people["viewer"]))
    import_task = detail.json()["import_task"]
    assert import_task["has_source"] is True
    assert "file_path" not in import_task


async def test_import_source_outside_uploads_is_not_served(client, db_session, data_dirs, people):
    outside = data_dirs["root"] / "config.json"
    outside.write_text("{}")
    task, _ = await _task_with_question(db_session, people, str(outside))
    response = await client.get(f"{API}/imports/{task.id}/source", headers=_auth(people["owner"]))
    assert response.status_code == 404


async def test_uploads_directory_is_no_longer_public(client, data_dirs):
    (data_dirs["uploads"] / "s3").mkdir()
    (data_dirs["uploads"] / "s3" / "paper.docx").write_bytes(b"x")
    response = await client.get("/uploads/s3/paper.docx")
    assert response.status_code != 200 or response.content != b"x"
