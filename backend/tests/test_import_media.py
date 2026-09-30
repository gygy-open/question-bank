"""导入流程接入媒体资产:文档内图片入库为学科资产、源文件进对象存储、签名凭据回传。"""
import io
import zipfile
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import select

from app.core import storage
from app.core.config import settings
from app.core.permissions import SubjectRole
from app.core.security import create_access_token
from app.models.import_task import ImportTask
from app.models.media_asset import MediaAsset, MediaPurpose
from app.models.subject import Subject
from app.models.user import User
from app.services.doc_processor import doc_processor
from app.services.importing.media import sign_source_ref, verify_source_ref
from app.services.question_content_converter import markdown_to_rich_doc

API = "/api/v1"


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (5, 3), "blue").save(buf, format="PNG")
    return buf.getvalue()


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    (tmp_path / "static").mkdir()
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def captured(monkeypatch):
    """替换抽取策略:记录送给 AI 的 markdown,不产出题目。"""
    seen: list[str] = []

    class FakeExtractor:
        async def extract(self, content, db, **kwargs):
            seen.append(content)
            return SimpleNamespace(questions=[], paper=None, stimuli=[], question_groups=[])

    monkeypatch.setattr(doc_processor, "_extractor_for", lambda method: FakeExtractor())
    return seen


@pytest.fixture
async def people(db_session, grant_role):
    editor = User(username="imp_editor", hashed_password="x", is_active=True)
    outsider = User(username="imp_outsider", hashed_password="x", is_active=True)
    subject = Subject(name="化学", slug="chem-import-media")
    db_session.add_all([editor, outsider, subject])
    await db_session.commit()
    await grant_role(editor, subject, SubjectRole.EDITOR)
    return {"editor": editor, "outsider": outsider, "subject": subject}


def test_converter_maps_asset_url_to_asset_id():
    doc = markdown_to_rich_doc("![图](/api/v1/media/42/content)")
    image = doc["content"][0]["content"][0]
    assert image["type"] == "image"
    assert image["attrs"]["assetId"] == 42
    assert image["attrs"]["src"] == "/api/v1/media/42/content"

    legacy = markdown_to_rich_doc("![图](/static/media/x/a.png)")
    assert "assetId" not in legacy["content"][0]["content"][0]["attrs"]


def test_source_ref_is_bound_to_user():
    sha = "a" * 64
    ref = sign_source_ref(sha, 1)
    assert verify_source_ref(ref, 1) == sha
    assert verify_source_ref(ref, 2) is None
    assert verify_source_ref(f"{'b' * 64}.{ref.split('.')[1]}", 1) is None
    assert verify_source_ref("../../etc/passwd", 1) is None
    assert verify_source_ref(None, 1) is None


async def test_archive_upload_stores_images_as_subject_assets(client, people, db_session, captured, data_dir):
    png = _png()
    archive = _zip({"q.md": b"# Q\n\n![fig](img/a.png)\n", "img/a.png": png})
    sid = people["subject"].id

    response = await client.post(
        f"{API}/upload/markdown-archive?method=structured&subject_id={sid}",
        files={"file": ("paper.zip", archive, "application/zip")},
        headers=_auth(people["editor"]),
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert "file_path" not in body
    asset = (await db_session.execute(select(MediaAsset))).scalars().one()
    assert asset.subject_id == sid
    assert asset.purpose == MediaPurpose.CONTENT
    assert storage.read_bytes(asset.sha256) == png
    assert f"![fig](/api/v1/media/{asset.id}/content)" in captured[0]
    # 源文件已进对象存储,凭据指向它;没有残留解压目录/媒体副本。
    source_sha = verify_source_ref(body["source_ref"], people["editor"].id)
    assert storage.read_bytes(source_sha) == archive
    assert not (data_dir / "uploads").exists() or not any((data_dir / "uploads").rglob("*"))
    assert not any((data_dir / "tmp" / "jobs").rglob("*"))


async def test_archive_upload_requires_subject_edit_permission(client, people, captured):
    archive = _zip({"q.md": b"![fig](a.png)", "a.png": _png()})

    response = await client.post(
        f"{API}/upload/markdown-archive?method=structured&subject_id={people['subject'].id}",
        files={"file": ("paper.zip", archive, "application/zip")},
        headers=_auth(people["outsider"]),
    )

    assert response.status_code == 403
    assert captured == []


async def test_archive_upload_with_images_but_no_subject_is_rejected(client, people, captured):
    archive = _zip({"q.md": b"![fig](a.png)", "a.png": _png()})

    response = await client.post(
        f"{API}/upload/markdown-archive?method=structured",
        files={"file": ("paper.zip", archive, "application/zip")},
        headers=_auth(people["editor"]),
    )

    assert response.status_code == 422


def _commit_payload(**extra) -> dict:
    payload = {
        "scope": "shared",
        "questions": [
            {
                "temp_id": "t1",
                "q_type": "free_response",
                "content": {
                    "type": "doc",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "题"}]}],
                },
                "answer": {"kind": "free_response", "reference": None},
                "status": "draft",
                "difficulty": 3,
                "visibility": "public",
            }
        ],
        "outline": [{"kind": "question_ref", "temp_id": "t1"}],
        "filename": "卷.md",
    }
    payload.update(extra)
    return payload


async def test_commit_links_verified_source_and_serves_it(client, people, db_session):
    sha = storage.put_bytes(b"# original paper")
    editor = people["editor"]

    response = await client.post(
        f"{API}/subjects/{people['subject'].id}/paper-imports",
        json=_commit_payload(source_ref=sign_source_ref(sha, editor.id)),
        headers=_auth(editor),
    )

    assert response.status_code == 200, response.text
    task = (await db_session.execute(select(ImportTask))).scalars().one()
    assert task.source_sha256 == sha
    assert task.file_path == "virtual"

    source = await client.get(f"{API}/imports/{task.id}/source", headers=_auth(editor))
    assert source.status_code == 200
    assert source.content == b"# original paper"
    assert source.headers["content-type"].startswith("text/markdown")


async def test_commit_ignores_source_ref_signed_for_another_user(client, people, db_session):
    sha = storage.put_bytes(b"someone else's paper")
    forged = sign_source_ref(sha, people["outsider"].id)

    response = await client.post(
        f"{API}/subjects/{people['subject'].id}/paper-imports",
        json=_commit_payload(source_ref=forged),
        headers=_auth(people["editor"]),
    )

    assert response.status_code == 200, response.text
    task = (await db_session.execute(select(ImportTask))).scalars().one()
    assert task.source_sha256 is None


async def test_batch_zip_import_records_subject_and_source_objects(client, people, db_session):
    editor = people["editor"]
    editor.last_active_subject_id = people["subject"].id
    await db_session.commit()
    archive = _zip({"a.md": b"![fig](p.png)", "b.md": b"plain", "p.png": _png()})

    response = await client.post(
        f"{API}/imports",
        files=[("files", ("set.zip", archive, "application/zip"))],
        headers=_auth(editor),
    )

    assert response.status_code == 200, response.text
    tasks = (
        await db_session.execute(select(ImportTask).order_by(ImportTask.original_filename))
    ).scalars().all()
    assert [t.original_filename for t in tasks] == ["set/a.md", "set/b.md"]
    asset = (await db_session.execute(select(MediaAsset))).scalars().one()
    for task in tasks:
        assert task.subject_id == people["subject"].id
        assert task.file_path == "virtual"
    assert storage.read_bytes(tasks[0].source_sha256) == (
        f"![fig](/api/v1/media/{asset.id}/content)".encode()
    )


async def test_batch_import_requires_active_subject(client, people):
    response = await client.post(
        f"{API}/imports",
        files=[("files", ("a.md", b"# q", "text/markdown"))],
        headers=_auth(people["editor"]),
    )

    assert response.status_code == 400
