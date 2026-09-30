"""P3:存量迁移、旧 URL 鉴权下发、导出解析旧路径、旧目录清理与对象回收。"""
import io
import json
import os
import time
import uuid
from datetime import datetime, timedelta

import pytest
from PIL import Image
from sqlalchemy import select

from app.core import storage
from app.core.config import settings
from app.core.security import create_access_token
from app.models.chat import ChatMessage, ChatSession
from app.models.composition import (
    Composition,
    CompositionNode,
    CompositionNodeKind,
    CompositionVersion,
    ScopeType,
)
from app.models.import_task import ImportTask, ImportTaskStatus
from app.models.media_asset import LegacyMediaPath, MediaAsset, MediaOwnerType, MediaReference
from app.models.question import Question, QuestionType
from app.models.stimulus import Stimulus
from app.models.subject import Subject
from app.models.user import User
from app.services import media_service
from app.services.exporting.images import ImageResolver
from app.services.media_gc import collect_garbage
from app.services.media_migration import migrate_media, purge_legacy_files

API = "/api/v1"


def _png(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (3, 3), color).save(buf, format="PNG")
    return buf.getvalue()


def _doc(src: str) -> dict:
    return {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "看图"}]},
            {"type": "image", "attrs": {"src": src, "alt": "图"}},
        ],
    }


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    media = tmp_path / "static" / "media"
    uploads = tmp_path / "uploads"
    media.mkdir(parents=True)
    uploads.mkdir()
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "MEDIA_DIR", media)
    monkeypatch.setattr(settings, "UPLOAD_DIR", uploads)
    return tmp_path


@pytest.fixture
async def legacy(db_session, data_dir):
    """一份典型的旧数据:题目、材料、稿件节点、定稿快照、头像、对话附图、导入源文件。"""
    media = settings.MEDIA_DIR
    (media / "task1").mkdir()
    (media / "task1" / "a b.png").write_bytes(_png("red"))
    (media / "images").mkdir()
    (media / "images" / "avatar.png").write_bytes(_png("green"))
    (media / "images" / "chat.png").write_bytes(_png("blue"))
    source = settings.UPLOAD_DIR / "s1" / "卷.md"
    source.parent.mkdir()
    source.write_text("# 原卷", encoding="utf-8")

    user = User(username="legacy_owner", hashed_password="x", is_active=True, avatar_url="/static/media/images/avatar.png")
    subject = Subject(name="地理", slug="geo-legacy")
    db_session.add_all([user, subject])
    await db_session.flush()

    src = "/static/media/task1/a%20b.png"
    question = Question(
        content=json.dumps(_doc(src)),
        analysis=json.dumps(_doc("/static/media/missing/gone.png")),
        q_type=QuestionType.FREE_RESPONSE,
        subject_id=subject.id,
        created_by=user.id,
    )
    stimulus = Stimulus(subject_id=subject.id, content=json.dumps(_doc(src)), created_by=user.id, updated_by=user.id)
    comp = Composition(title="旧稿", scope_type=ScopeType.SHARED, subject_id=subject.id, created_by=user.id, updated_by=user.id)
    db_session.add_all([question, stimulus, comp])
    await db_session.flush()
    node = CompositionNode(
        id=str(uuid.uuid4()), composition_id=comp.id, position=0,
        node_kind=CompositionNodeKind.BLOCK, node_type="rich_text", content=_doc(src),
    )
    version = CompositionVersion(
        composition_id=comp.id, version_no=1, source_revision=1, title="旧稿", subject_id=subject.id,
        snapshot={"nodes": [{"node_type": "rich_text", "content": _doc(src)}]}, finalized_by=user.id,
    )
    session = ChatSession(user_id=user.id)
    db_session.add_all([node, version, session])
    await db_session.flush()
    db_session.add(ChatMessage(session_id=session.id, role="user", content="看", images=["/static/media/images/chat.png"]))
    task = ImportTask(
        user_id=user.id, file_path=str(source), original_filename="卷.md", file_type="markdown",
        status=ImportTaskStatus.COMPLETED,
    )
    db_session.add(task)
    await db_session.commit()
    return {
        "user": user, "subject": subject, "question": question, "stimulus": stimulus,
        "comp": comp, "node": node, "version": version, "task": task, "src": src, "source": source,
    }


def _image_attrs(raw) -> dict:
    doc = json.loads(raw) if isinstance(raw, str) else raw
    return next(media_service.iter_image_attrs(doc))


async def test_dry_run_changes_nothing(db_session, legacy):
    report = await migrate_media(db_session, apply=False)

    assert report.questions_updated == 1 and report.assets_created == 1
    assert (await db_session.scalars(select(LegacyMediaPath))).all() == []
    assert (await db_session.scalars(select(MediaAsset))).all() == []
    await db_session.refresh(legacy["question"])
    assert "assetId" not in _image_attrs(legacy["question"].content)


async def test_migration_links_assets_and_is_idempotent(db_session, legacy):
    report = await migrate_media(db_session, apply=True)

    assert report.legacy_paths_mapped == 3  # 内容图 + 头像 + 对话附图
    assert report.assets_created == 1
    assert (report.questions_updated, report.stimuli_updated, report.nodes_updated) == (1, 1, 1)
    assert report.versions_indexed == 1
    assert report.import_sources_stored == 1
    assert report.missing == {"/static/media/missing/gone.png"}

    asset = (await db_session.scalars(select(MediaAsset))).one()
    assert asset.subject_id == legacy["subject"].id and asset.original_filename == "a b.png"
    for obj, field in ((legacy["question"], "content"), (legacy["stimulus"], "content"), (legacy["node"], "content")):
        await db_session.refresh(obj)
        attrs = _image_attrs(getattr(obj, field))
        assert attrs == {"src": legacy["src"], "alt": "图", "assetId": asset.id}
    await db_session.refresh(legacy["version"])
    assert "assetId" not in _image_attrs(legacy["version"].snapshot)

    owners = set((await db_session.execute(select(MediaReference.owner_type, MediaReference.owner_id))).all())
    assert owners == {
        (MediaOwnerType.QUESTION.value, legacy["question"].id),
        (MediaOwnerType.STIMULUS.value, legacy["stimulus"].id),
        (MediaOwnerType.COMPOSITION.value, legacy["comp"].id),
        (MediaOwnerType.COMPOSITION_VERSION.value, legacy["version"].id),
    }
    await db_session.refresh(legacy["task"])
    assert storage.read_bytes(legacy["task"].source_sha256) == legacy["source"].read_bytes()

    again = await migrate_media(db_session, apply=True)
    assert (again.legacy_paths_mapped, again.assets_created, again.questions_updated) == (0, 0, 0)
    assert again.import_sources_stored == 0


async def test_purge_then_legacy_urls_still_resolve(client, db_session, legacy, data_dir):
    await migrate_media(db_session, apply=True)
    stray = settings.MEDIA_DIR / "unreferenced.png"
    stray.write_bytes(_png("black"))

    preview = await purge_legacy_files(db_session, apply=False)
    assert len(preview.media_removed) == 3 and len(preview.uploads_removed) == 1
    assert preview.kept_unmapped == [stray]
    assert (settings.MEDIA_DIR / "task1" / "a b.png").exists()

    await purge_legacy_files(db_session, apply=True)
    assert sorted(p.name for p in settings.MEDIA_DIR.rglob("*")) == ["unreferenced.png"]
    assert not any(settings.UPLOAD_DIR.rglob("*"))

    user = legacy["user"]
    headers = {"Authorization": f"Bearer {create_access_token(subject=user.id)}"}
    served = await client.get(legacy["src"], headers=headers)
    assert served.status_code == 200
    assert served.content == _png("red") and served.headers["content-type"] == "image/png"
    assert (await client.get(legacy["src"])).status_code == 401
    assert (await client.get("/static/media/nope.png", headers=headers)).status_code == 404

    source = await client.get(f"{API}/imports/{legacy['task'].id}/source", headers=headers)
    assert source.status_code == 200 and "原卷" in source.text

    from app.api.v1.endpoints.chat import get_image_base64
    assert (await get_image_base64(db_session, "/static/media/images/chat.png")).startswith("data:image/png")

    snapshot = legacy["version"].snapshot
    resolver = ImageResolver(legacy=await media_service.resolve_legacy_images(
        db_session, media_service.collect_legacy_paths(snapshot)
    ))
    resolved = resolver.resolve_image(_image_attrs(snapshot))
    assert resolved is not None and resolved.path.read_bytes() == _png("red") and resolved.suffix == ".png"


def _age(path, days: int) -> None:
    old = time.time() - days * 86400
    os.utime(path, (old, old))


async def test_gc_keeps_referenced_and_recent_objects(db_session, legacy):
    await migrate_media(db_session, apply=True)
    orphan_old = storage.object_path(storage.put_bytes(b"orphan-old"))
    orphan_new = storage.object_path(storage.put_bytes(b"orphan-new"))
    for _, path in storage.iter_objects():
        _age(path, 30)
    os.utime(orphan_new)

    asset = (await db_session.scalars(select(MediaAsset))).one()
    unused = await media_service.ingest(
        db_session, _png("white"), purpose=media_service.MediaPurpose.CONTENT, actor_id=None,
        subject_id=legacy["subject"].id,
    )
    unused.deleted_at = datetime.utcnow() - timedelta(days=30)
    unused_id, unused_path = unused.id, storage.object_path(unused.sha256)
    kept_sha = asset.sha256
    await db_session.commit()
    _age(unused_path, 30)

    preview = await collect_garbage(db_session, apply=False)
    assert set(preview.orphan_objects) == {orphan_old, unused_path}
    assert preview.deleted_assets == [unused_id]
    assert orphan_old.exists() and await db_session.get(MediaAsset, unused_id) is not None

    await collect_garbage(db_session, apply=True)
    assert not orphan_old.exists() and not unused_path.exists()
    assert orphan_new.exists()
    assert storage.exists(kept_sha)
    db_session.expire_all()
    assert await db_session.get(MediaAsset, unused_id) is None
