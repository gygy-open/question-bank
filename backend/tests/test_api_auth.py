from app.core.security import create_access_token, get_password_hash
from app.models.user import User


async def _seed_user(db_session, *, username="alice", password="s3cret", is_active=True) -> User:
    user = User(
        username=username,
        full_name="Alice",
        hashed_password=get_password_hash(password),
        is_active=is_active,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def test_protected_endpoint_without_token_is_unauthorized(client):
    resp = await client.post("/api/v1/login/test-token")

    assert resp.status_code == 401


async def test_protected_endpoint_with_invalid_token_is_forbidden(client):
    resp = await client.post(
        "/api/v1/login/test-token",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )

    assert resp.status_code == 403


async def test_valid_token_for_missing_user_returns_404(client):
    token = create_access_token(subject=999999)
    resp = await client.post(
        "/api/v1/login/test-token",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 404


async def test_login_happy_path_returns_usable_token(client, db_session):
    await _seed_user(db_session, username="bob", password="hunter2")

    login = await client.post(
        "/api/v1/login/access-token",
        data={"username": "bob", "password": "hunter2"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = await client.post(
        "/api/v1/login/test-token",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200
    assert me.json()["username"] == "bob"


async def test_login_with_wrong_password_is_rejected(client, db_session):
    await _seed_user(db_session, username="carol", password="correct")

    resp = await client.post(
        "/api/v1/login/access-token",
        data={"username": "carol", "password": "wrong"},
    )

    assert resp.status_code == 400
