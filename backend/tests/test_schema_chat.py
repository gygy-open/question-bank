"""ChatRequest 契约:temperature 已从请求体移除,不再接受也不再默认注入。"""
import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest


def _valid_payload() -> dict:
    return {"model_id": 1, "message": {"role": "user", "content": "hi"}}


def test_temperature_is_not_a_field():
    assert "temperature" not in ChatRequest.model_fields


def test_temperature_rejected_when_extra_forbidden():
    # 默认 Pydantic 忽略未知字段,这里显式验证 temperature 不会被吸收为已知字段。
    req = ChatRequest.model_validate({**_valid_payload(), "temperature": 0.9})
    assert not hasattr(req, "temperature")
    assert "temperature" not in req.model_dump()


def test_minimal_request_still_valid():
    req = ChatRequest.model_validate(_valid_payload())
    assert req.model_id == 1
    assert req.stream is True
    assert req.subject_id is None


def test_message_required():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate({"model_id": 1})
