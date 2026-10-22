"""API Key 等敏感配置的对称加密。

密钥由 SECRET_KEY 派生；密文带 ``enc:v1:`` 前缀，便于与历史明文区分。
SECRET_KEY 变化后旧密文无法解开，此时 :func:`decrypt_secret` 抛 :class:`SecretDecryptError`，
由调用方提示用户重新填写。
"""
import base64
import hashlib
from functools import lru_cache
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_PREFIX = "enc:v1:"


class SecretDecryptError(Exception):
    pass


@lru_cache(maxsize=4)
def _fernet(secret_key: str) -> Fernet:
    digest = hashlib.sha256(f"qb-secret-v1:{secret_key}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def is_encrypted(value: Optional[str]) -> bool:
    return bool(value) and value.startswith(_PREFIX)


def encrypt_secret(value: str) -> str:
    if not value or is_encrypted(value):
        return value
    token = _fernet(settings.SECRET_KEY).encrypt(value.encode()).decode()
    return f"{_PREFIX}{token}"


def decrypt_secret(value: Optional[str]) -> str:
    if not value:
        return ""
    if not is_encrypted(value):
        return value  # 历史明文
    try:
        return _fernet(settings.SECRET_KEY).decrypt(value[len(_PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise SecretDecryptError("API Key 无法解密，可能是服务密钥已变更，请重新填写") from exc
