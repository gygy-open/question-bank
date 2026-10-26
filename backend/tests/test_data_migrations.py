"""启动后一次性数据迁移:标记、结构版本检查、失败重试与历史媒体迁移。"""
import asyncio
import io
import json
import os

import pytest
from PIL import Image
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app import worker
from app.core.config import settings
from app.models.media_asset import MediaAsset
from app.models.question import Question, QuestionType
from app.models.subject import Subject
from app.models.system_setting import SystemSetting
from app.services import data_migrations
from app.services.data_migrations import DataMigration, Outcome, run_pending

MYSQL_TEST_URL = os.getenv("MYSQL_TEST_URL")


@pytest.fixture
def maker(engine):
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    media = tmp_path / "static" / "media"
    media.mkdir(parents=True)
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(settings, "MEDIA_DIR", media)
    return tmp_path


def _counting(name: str, calls: list, *, fail: bool = False) -> DataMigration:
    async def run(db):
        calls.append(name)
        db.add(SystemSetting(key=f"side_effect.{name}", value="x"))
        await db.flush()
        if fail:
            raise RuntimeError("boom")
        return f"{name} ok"

    return DataMigration(name, run)


async def test_runs_each_pending_migration_once_and_records_flag(engine, maker, db_session):
    calls: list = []
    migrations = [_counting("first", calls), _counting("second", calls)]

    assert await run_pending(engine=engine, sessionmaker=maker, migrations=migrations, require_head=False) is Outcome.DONE
    assert await run_pending(engine=engine, sessionmaker=maker, migrations=migrations, require_head=False) is Outcome.DONE

    assert calls == ["first", "second"]
    flag = await db_session.get(SystemSetting, "data_migration.first")
    assert flag.value and flag.description == "first ok"


async def test_failure_rolls_back_writes_no_flag_and_stops(engine, maker, db_session):
    calls: list = []
    migrations = [_counting("broken", calls, fail=True), _counting("later", calls)]

    outcome = await run_pending(engine=engine, sessionmaker=maker, migrations=migrations, require_head=False)

    assert outcome is Outcome.FAILED
    assert calls == ["broken"]
    assert await db_session.get(SystemSetting, "data_migration.broken") is None
    assert await db_session.get(SystemSetting, "side_effect.broken") is None


async def _set_alembic_version(engine, *revs):
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        await conn.execute(text("DELETE FROM alembic_version"))
        for rev in revs:
            await conn.execute(text("INSERT INTO alembic_version VALUES (:r)"), {"r": rev})


async def test_waits_for_schema_head(engine, maker):
    from alembic.script import ScriptDirectory

    from app.db.migrations import _alembic_config

    script = ScriptDirectory.from_config(_alembic_config())
    head = script.get_current_head()
    behind = script.get_revision(head).down_revision
    behind = behind[0] if isinstance(behind, tuple) else behind
    calls: list = []
    migrations = [_counting("needs_head", calls)]

    async def run():
        return await run_pending(engine=engine, sessionmaker=maker, migrations=migrations)

    assert await run() is Outcome.NOT_READY  # 还没有 alembic_version 表
    await _set_alembic_version(engine, behind)
    assert await run() is Outcome.NOT_READY
    await _set_alembic_version(engine, "ffffffffffff")
    assert await run() is Outcome.SKIPPED  # 库比代码新
    assert calls == []
    await _set_alembic_version(engine, head)
    assert await run() is Outcome.DONE
    assert calls == ["needs_head"]


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(buf, format="PNG")
    return buf.getvalue()


async def test_legacy_media_assets_shows_old_images_in_media_library(engine, maker, db_session):
    (settings.MEDIA_DIR / "task1").mkdir()
    (settings.MEDIA_DIR / "task1" / "fig.png").write_bytes(_png())
    subject = Subject(name="历史", slug="history-dm")
    db_session.add(subject)
    await db_session.flush()
    doc = {"type": "doc", "content": [{"type": "image", "attrs": {"src": "/static/media/task1/fig.png"}}]}
    question = Question(content=json.dumps(doc), q_type=QuestionType.FREE_RESPONSE, subject_id=subject.id)
    db_session.add(question)
    await db_session.commit()

    assert await run_pending(engine=engine, sessionmaker=maker, require_head=False) is Outcome.DONE

    assets = (await db_session.scalars(select(MediaAsset).where(MediaAsset.subject_id == subject.id))).all()
    assert len(assets) == 1 and assets[0].source == "migration"
    flag = await db_session.get(SystemSetting, "data_migration.legacy_media_assets")
    assert flag is not None and "新建资产 1" in flag.description


async def test_worker_retries_until_ready(monkeypatch):
    outcomes = iter([Outcome.NOT_READY, Outcome.NOT_READY, Outcome.DONE])
    seen = []

    async def fake_run_pending():
        seen.append(1)
        return next(outcomes)

    monkeypatch.setattr(data_migrations, "run_pending", fake_run_pending)
    await worker.run_data_migrations(retry_interval=0)
    assert len(seen) == 3


async def test_worker_gives_up_after_max_attempts(monkeypatch):
    seen = []

    async def fake_run_pending():
        seen.append(1)
        return Outcome.NOT_READY

    monkeypatch.setattr(data_migrations, "run_pending", fake_run_pending)
    await worker.run_data_migrations(retry_interval=0, max_attempts=3)
    assert len(seen) == 3


def test_flag_key_respects_column_length():
    for migration in data_migrations.DATA_MIGRATIONS:
        data_migrations.flag_key(migration.name)
    with pytest.raises(ValueError):
        data_migrations.flag_key("x" * 60)


@pytest.mark.skipif(not MYSQL_TEST_URL, reason="MYSQL_TEST_URL not set (needs a real MySQL)")
async def test_mysql_lock_lets_only_one_process_run():
    engine_a = create_async_engine(MYSQL_TEST_URL)
    engine_b = create_async_engine(MYSQL_TEST_URL)
    try:
        async with data_migrations._exclusive(engine_a) as first:
            async with data_migrations._exclusive(engine_b) as second:
                assert first is True and second is False
        async with data_migrations._exclusive(engine_b) as again:
            assert again is True
    finally:
        await asyncio.gather(engine_a.dispose(), engine_b.dispose())


async def test_flags_are_hidden_from_settings_api_and_read_only(client, db_session):
    from app.core.security import create_access_token
    from app.models.user import User

    admin = User(username="dm_admin", hashed_password="x", is_active=True, is_superuser=True)
    db_session.add(admin)
    db_session.add(SystemSetting(key="data_migration.legacy_media_assets", value="2026-01-01T00:00:00+00:00"))
    # 下划线在 LIKE 中是通配符,确认没有误伤形似的普通键。
    db_session.add(SystemSetting(key="dataXmigration.lookalike", value="v"))
    await db_session.commit()
    headers = {"Authorization": "Bearer " + create_access_token(admin.id)}

    listed = await client.get("/api/v1/settings", headers=headers)
    assert listed.status_code == 200
    keys = {s["key"] for s in listed.json()}
    assert "data_migration.legacy_media_assets" not in keys
    assert "dataXmigration.lookalike" in keys

    put = await client.put(
        "/api/v1/settings/data_migration.legacy_media_assets", headers=headers, json={"value": "x"}
    )
    assert put.status_code == 403
    flag = await db_session.get(SystemSetting, "data_migration.legacy_media_assets")
    await db_session.refresh(flag)
    assert flag.value.startswith("2026")
