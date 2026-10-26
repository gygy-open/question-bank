"""First-admin initialization, decoupled from database configuration."""
import asyncio

import pytest

import app.api.v1.endpoints.setup as setup_endpoints
from app.models.user import User
from app.services import setup_state

API = "/api/v1"


@pytest.fixture
def fresh_install(setup_sessionmaker, monkeypatch):
    """Database configured (e.g. Docker DB_URL) but no administrator yet."""
    monkeypatch.setattr(setup_endpoints, "is_configured", lambda: True)
    setup_state.reset_admin_ready()


async def _seed_user(db_session, *, username, is_superuser=False, is_active=True) -> User:
    user = User(
        username=username, full_name=username, hashed_password="x",
        is_active=is_active, is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_status_reports_both_stages(client, fresh_install):
    resp = await client.get(f"{API}/setup/status")
    assert resp.json() == {"db_configured": True, "admin_initialized": False}

    await client.post(f"{API}/setup/admin", json={"username": "root", "password": "secret1"})

    resp = await client.get(f"{API}/setup/status")
    assert resp.json() == {"db_configured": True, "admin_initialized": True}


async def test_status_without_database(client, monkeypatch):
    monkeypatch.setattr(setup_endpoints, "is_configured", lambda: False)
    resp = await client.get(f"{API}/setup/status")
    assert resp.json() == {"db_configured": False, "admin_initialized": False}


async def test_create_first_admin(client, db_session, fresh_install):
    resp = await client.post(
        f"{API}/setup/admin", json={"username": "  root  ", "password": "secret1"}
    )
    assert resp.status_code == 200

    login = await client.post(
        f"{API}/login/access-token", data={"username": "root", "password": "secret1"}
    )
    assert login.status_code == 200


async def test_create_admin_rejected_once_initialized(client, db_session, fresh_install):
    await _seed_user(db_session, username="boss", is_superuser=True)

    resp = await client.post(f"{API}/setup/admin", json={"username": "x", "password": "secret1"})
    assert resp.status_code == 400


async def test_inactive_superuser_does_not_count(client, db_session, fresh_install):
    await _seed_user(db_session, username="old", is_superuser=True, is_active=False)

    resp = await client.post(f"{API}/setup/admin", json={"username": "root", "password": "secret1"})
    assert resp.status_code == 200


async def test_create_admin_rejects_taken_username(client, db_session, fresh_install):
    await _seed_user(db_session, username="taken")

    resp = await client.post(f"{API}/setup/admin", json={"username": "taken", "password": "secret1"})
    assert resp.status_code == 400


async def test_create_admin_requires_database(client, monkeypatch):
    monkeypatch.setattr(setup_endpoints, "is_configured", lambda: False)
    resp = await client.post(f"{API}/setup/admin", json={"username": "root", "password": "secret1"})
    assert resp.status_code == 400


async def test_concurrent_creation_only_one_wins(client, fresh_install):
    results = await asyncio.gather(
        client.post(f"{API}/setup/admin", json={"username": "a1", "password": "secret1"}),
        client.post(f"{API}/setup/admin", json={"username": "a2", "password": "secret1"}),
    )
    assert sorted(r.status_code for r in results) == [200, 400]


async def test_configure_database_rejected_when_configured(client, monkeypatch):
    monkeypatch.setattr(setup_endpoints, "is_configured", lambda: True)
    resp = await client.post(f"{API}/setup/database", json={"db_type": "sqlite"})
    assert resp.status_code == 400


def _stub_database_setup(monkeypatch, calls, *, migrate_error=None):
    async def _conn(url):
        calls.append("test")

    def _migrate(url):
        calls.append("migrate")
        if migrate_error:
            raise migrate_error

    async def _reset(url):
        calls.append("reset")

    monkeypatch.setattr(setup_endpoints, "is_configured", lambda: False)
    monkeypatch.setattr(setup_endpoints, "_test_connection", _conn)
    monkeypatch.setattr(setup_endpoints, "run_migrations", _migrate)
    monkeypatch.setattr(setup_endpoints, "save_runtime_config", lambda cfg: calls.append("save"))
    monkeypatch.setattr(setup_endpoints, "reset_engine", _reset)


async def test_configure_database_migrates_before_persisting(client, monkeypatch):
    calls: list = []
    _stub_database_setup(monkeypatch, calls)

    resp = await client.post(f"{API}/setup/database", json={"db_type": "sqlite"})

    assert resp.status_code == 200
    assert calls == ["test", "migrate", "save", "reset"]


async def test_failed_migration_does_not_persist_config(client, monkeypatch):
    calls: list = []
    _stub_database_setup(monkeypatch, calls, migrate_error=RuntimeError("boom"))

    resp = await client.post(f"{API}/setup/database", json={"db_type": "sqlite"})

    assert resp.status_code == 500
    assert "save" not in calls
