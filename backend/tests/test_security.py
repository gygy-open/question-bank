from datetime import timedelta

from jose import jwt

from app.core.config import settings
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = get_password_hash("s3cret")

    assert hashed != "s3cret"
    assert verify_password("s3cret", hashed) is True
    assert verify_password("wrong", hashed) is False


def test_access_token_encodes_subject():
    token = create_access_token(subject=42)
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    assert payload["sub"] == "42"
    assert "exp" in payload


def test_access_token_respects_expiry_delta():
    short = jwt.decode(
        create_access_token(subject="a", expires_delta=timedelta(minutes=1)),
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )
    long = jwt.decode(
        create_access_token(subject="a", expires_delta=timedelta(minutes=60)),
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    assert long["exp"] > short["exp"]
