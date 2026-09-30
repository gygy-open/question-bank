import io
import json

import pytest
from PIL import Image

from app.core import storage
from app.core.config import settings
from app.core.permissions import SubjectRole
from app.core.security import create_access_token
from app.models.media_asset import MediaAsset, MediaPurpose
from app.models.subject import Subject
from app.models.user import User
from app.services import media_service
from app.capabilities.errors import Unprocessable

API = "/api/v1"


def _token(user: User) -> str:
    return create_access_token(subject=user.id)


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {_token(user)}"}


def _image_bytes(fmt: str = "PNG", color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (6, 4), color).save(buf, format=fmt)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    # app.main 可能在本测试中首次导入,/static 挂载要求目录存在。
    (tmp_path / "static").mkdir()
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    return tmp_path


@pytest.fixture
async def people(db_session, grant_role):
    editor = User(username="media_editor", hashed_password="x", is_active=True)
    viewer = User(username="media_viewer", hashed_password="x", is_active=True)
    outsider = User(username="media_outsider", hashed_password="x", is_active=True)
    subject = Subject(name="地理", slug="geo-media")
    other_subject = Subject(name="物理", slug="phy-media")
    db_session.add_all([editor, viewer, outsider, subject, other_subject])
    await db_session.commit()
    await grant_role(editor, subject, SubjectRole.EDITOR)
    await grant_role(viewer, subject, SubjectRole.VIEWER)
    return {
        "editor": editor,
        "viewer": viewer,
        "outsider": outsider,
        "subject": subject,
        "other_subject": other_subject,
    }


# --- storage ---------------------------------------------------------------

def test_storage_is_content_addressed_and_idempotent(data_dir):
    sha = storage.put_bytes(b"hello")
    assert storage.object_path(sha) == data_dir / "storage" / "objects" / sha[:2] / sha[2:4] / sha
    assert storage.put_bytes(b"hello") == sha
    assert storage.read_bytes(sha) == b"hello"
    assert not list((data_dir / "tmp" / "staging").iterdir())


def test_storage_rejects_malformed_keys():
    with pytest.raises(storage.StorageError):
        storage.object_path("../../etc/passwd")


def test_job_dir_is_removed_after_use(data_dir):
    with storage.job_dir() as job:
        (job / "work.md").write_text("x")
        path = job
    assert not path.exists()


# --- media_service ---------------------------------------------------------

def test_sniff_accepts_web_images_and_rejects_others():
    assert media_service.sniff(_image_bytes("PNG")).mime == "image/png"
    assert media_service.sniff(_image_bytes("JPEG")).mime == "image/jpeg"
    for data in (b"<script>alert(1)</script>", b"<svg xmlns='http://www.w3.org/2000/svg'/>"):
        with pytest.raises(Unprocessable):
            media_service.sniff(data)
    with pytest.raises(Unprocessable):
        media_service.sniff(_image_bytes("BMP"))


def test_sniff_accepts_legacy_formats_only_from_imports():
    emf = b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF" + b"\x00" * 64
    assert media_service.sniff(emf, allow_legacy_formats=True).mime == "image/emf"
    assert media_service.sniff(_image_bytes("BMP"), allow_legacy_formats=True).mime == "image/bmp"
    assert not media_service.is_displayable("image/emf")
    with pytest.raises(Unprocessable):
        media_service.sniff(emf)


async def test_ingest_deduplicates_within_scope(db_session, people):
    subject = people["subject"]
    data = _image_bytes()
    first = await media_service.ingest(
        db_session, data, purpose=MediaPurpose.CONTENT, subject_id=subject.id, actor_id=people["editor"].id, filename="a.png"
    )
    again = await media_service.ingest(
        db_session, data, purpose=MediaPurpose.CONTENT, subject_id=subject.id, actor_id=people["viewer"].id
    )
    other = await media_service.ingest(
        db_session, data, purpose=MediaPurpose.CONTENT, subject_id=people["other_subject"].id, actor_id=people["editor"].id
    )
    assert again.id == first.id
    assert other.id != first.id and other.sha256 == first.sha256
    assert first.width == 6 and first.height == 4 and first.original_filename == "a.png"


async def test_ingest_requires_subject_for_content(db_session, people):
    with pytest.raises(Unprocessable):
        await media_service.ingest(db_session, _image_bytes(), purpose=MediaPurpose.CONTENT, actor_id=people["editor"].id)


def test_collect_asset_ids_walks_nested_json():
    doc = {
        "nodes": [
            {"content": {"type": "doc", "content": [{"type": "image", "attrs": {"assetId": 3}}]}},
            {"options": [{"content": {"type": "doc", "content": [{"type": "image", "attrs": {"assetId": 5, "src": "/x"}}]}}]},
            {"type": "image", "attrs": {"assetId": True}},
        ]
    }
    assert media_service.collect_asset_ids(doc) == {3, 5}


# --- API -------------------------------------------------------------------

async def _upload(client, people, user_key="editor"):
    return await client.post(
        f"{API}/subjects/{people['subject'].id}/media",
        files={"file": ("图.png", _image_bytes(), "image/png")},
        headers=_auth(people[user_key]),
    )


async def test_subject_upload_requires_edit_permission(client, people):
    assert (await _upload(client, people, "viewer")).status_code == 403
    created = await _upload(client, people)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["url"] == f"/api/v1/media/{body['id']}/content"
    assert body["displayable"] is True and body["mime"] == "image/png"


async def test_upload_rejects_disguised_files(client, people):
    response = await client.post(
        f"{API}/subjects/{people['subject'].id}/media",
        files={"file": ("x.png", b"<html>hi</html>", "image/png")},
        headers=_auth(people["editor"]),
    )
    assert response.status_code == 422


async def test_content_is_served_by_header_or_cookie_with_subject_permission(client, people):
    asset = (await _upload(client, people)).json()
    url = f"{API}/media/{asset['id']}/content"

    by_header = await client.get(url, headers=_auth(people["viewer"]))
    assert by_header.status_code == 200
    assert by_header.content == _image_bytes()
    assert by_header.headers["content-type"] == "image/png"
    assert by_header.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in by_header.headers["cache-control"]

    client.cookies.set("token", _token(people["viewer"]))
    try:
        assert (await client.get(url)).status_code == 200
    finally:
        client.cookies.clear()

    assert (await client.get(url, headers=_auth(people["outsider"]))).status_code == 404
    assert (await client.get(url)).status_code == 401


async def test_chat_media_is_private_and_avatar_is_shared(client, people):
    chat = await client.post(
        f"{API}/media/me?purpose=chat",
        files={"file": ("c.png", _image_bytes(color="blue"), "image/png")},
        headers=_auth(people["viewer"]),
    )
    avatar = await client.post(
        f"{API}/media/me?purpose=avatar",
        files={"file": ("a.png", _image_bytes(color="green"), "image/png")},
        headers=_auth(people["viewer"]),
    )
    assert chat.status_code == 201 and avatar.status_code == 201
    chat_url = f"{API}/media/{chat.json()['id']}/content"
    avatar_url = f"{API}/media/{avatar.json()['id']}/content"
    assert (await client.get(chat_url, headers=_auth(people["viewer"]))).status_code == 200
    assert (await client.get(chat_url, headers=_auth(people["outsider"]))).status_code == 404
    assert (await client.get(avatar_url, headers=_auth(people["outsider"]))).status_code == 200


async def test_rich_doc_rejects_invalid_asset_id():
    from app.services.question_content import validate_rich_doc

    doc = {"type": "doc", "content": [{"type": "image", "attrs": {"assetId": "1"}}]}
    with pytest.raises(ValueError):
        validate_rich_doc(doc)
    validate_rich_doc({"type": "doc", "content": [{"type": "image", "attrs": {"assetId": 1}}]})


async def test_export_resolver_prefers_asset_ids(db_session, people):
    from app.services.exporting.images import ImageResolver

    asset = await media_service.ingest(
        db_session, _image_bytes(), purpose=MediaPurpose.CONTENT, subject_id=people["subject"].id, actor_id=people["editor"].id
    )
    await db_session.commit()
    images = await media_service.load_content_images(db_session, {asset.id, 999}, subject_id=people["subject"].id)
    assert set(images) == {asset.id}
    assert await media_service.load_content_images(db_session, {asset.id}, subject_id=people["other_subject"].id) == {}

    resolved = ImageResolver(images).resolve_image({"assetId": asset.id})
    assert resolved is not None and resolved.suffix == ".png" and resolved.path.is_file()
    assert ImageResolver(images).resolve_image({"assetId": 999}) is None
