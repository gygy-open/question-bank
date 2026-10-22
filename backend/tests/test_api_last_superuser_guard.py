"""The API must never leave the system without an active superuser."""
from app.core.security import create_access_token
from app.models.user import User

API = "/api/v1"


async def _seed_user(db_session, *, username, is_superuser=False) -> User:
    user = User(
        username=username, full_name=username, hashed_password="x",
        is_active=True, is_superuser=is_superuser,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


async def test_cannot_delete_last_superuser(client, db_session):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)
    resp = await client.delete(f"{API}/users/{admin.id}", headers=_auth(admin))
    assert resp.status_code == 400


async def test_cannot_demote_or_deactivate_last_superuser(client, db_session):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)

    for body in ({"is_superuser": False}, {"is_active": False}):
        resp = await client.put(f"{API}/users/{admin.id}", json=body, headers=_auth(admin))
        assert resp.status_code == 400
        resp = await client.put(f"{API}/users/me", json=body, headers=_auth(admin))
        assert resp.status_code == 400


async def test_other_updates_to_last_superuser_allowed(client, db_session):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)
    resp = await client.put(
        f"{API}/users/{admin.id}", json={"full_name": "Boss"}, headers=_auth(admin)
    )
    assert resp.status_code == 200


async def test_can_remove_superuser_when_another_remains(client, db_session):
    admin = await _seed_user(db_session, username="admin", is_superuser=True)
    other = await _seed_user(db_session, username="admin2", is_superuser=True)

    resp = await client.put(
        f"{API}/users/{other.id}", json={"is_superuser": False}, headers=_auth(admin)
    )
    assert resp.status_code == 200
    resp = await client.delete(f"{API}/users/{other.id}", headers=_auth(admin))
    assert resp.status_code == 200
