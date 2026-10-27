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


def test_model_slot_refs_are_translated():
    from app.services.ai_config_service import ACTIVE_MODEL_SLOT_REFS

    refs = json.loads(ZH_CN.read_text(encoding="utf-8"))["apiErrors"]["refs"]
    for ref in ACTIVE_MODEL_SLOT_REFS.values():
        node = refs
        for part in ref.split("."):
            node = node[part]
        assert isinstance(node, str)


async def test_ai_config_domain_errors_carry_code_and_ref_params(db_session):
    import pytest

    from app.capabilities.errors import Invalid
    from app.services.ai_config_service import validate_active_model

    with pytest.raises(Invalid) as bad_id:
        await validate_active_model(db_session, key="AI_VISION_MODEL_ID", value="abc")
    assert bad_id.value.code == ErrorCode.AI_CONFIG_ACTIVE_ID_INVALID
    assert bad_id.value.params == {"target_ref": "model_slot.vision"}

    with pytest.raises(Invalid) as missing:
        await validate_active_model(db_session, key="AI_TEXT_MODEL_ID", value="999999")
    assert missing.value.code == ErrorCode.AI_CONFIG_ACTIVE_MODEL_NOT_FOUND


async def test_missing_authorization_header_has_code(client):
    resp = await client.get(f"{API}/users/me")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == ErrorCode.AUTH_NOT_AUTHENTICATED
    assert body["detail"] == "Not authenticated"
    assert resp.headers["www-authenticate"] == "Bearer"


async def test_validation_error_has_code_and_never_echoes_input(client):
    resp = await client.post(
        f"{API}/login/access-token",
        data={"username": "someone"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == ErrorCode.VALIDATION_FAILED
    assert isinstance(body["detail"], list)
    first = body["detail"][0]
    assert first["type"] == "missing"
    assert first["loc"][-1] == "password"
    assert "input" not in first

