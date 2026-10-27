"""错误码契约:响应带 code,且每个错误码在前端 zh-CN 里都有翻译。"""
import json
from pathlib import Path

from app.core.api_errors import ErrorCode

API = "/api/v1"
ZH_CN = Path(__file__).resolve().parents[2] / "frontend" / "i18n" / "locales" / "zh-CN.json"


def test_every_error_code_has_zh_cn_translation():
    messages = json.loads(ZH_CN.read_text(encoding="utf-8"))["apiErrors"]
    missing = []
    for code in ErrorCode:
        node = messages
        for part in str(code).split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if not isinstance(node, str):
            missing.append(str(code))
    assert not missing, f"apiErrors 缺少翻译: {missing}"


async def test_invalid_token_response_has_code_and_detail(client):
    resp = await client.get(f"{API}/users/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_TOKEN_INVALID
    assert body["detail"] == "Could not validate credentials"


async def test_login_wrong_credentials_has_code(client):
    resp = await client.post(
        f"{API}/login/access-token", data={"username": "nobody", "password": "x"}
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == ErrorCode.AUTH_INVALID_CREDENTIALS
