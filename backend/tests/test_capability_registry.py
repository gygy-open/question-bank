"""能力注册表的契约测试 —— 守住「新增能力不许漏权限」这条线。"""
import pytest

from app import capabilities
from app.capabilities.base import Authz, Scope
from app.capabilities.errors import (
    Conflict,
    DomainError,
    Forbidden,
    Invalid,
    NotFound,
    Unprocessable,
    status_for,
)
from app.capabilities.registry import UNGATED_ALLOWLIST


def test_names_are_unique_and_namespaced():
    names = [cap.name for cap in capabilities.all_capabilities()]
    assert len(names) == len(set(names))
    for name in names:
        assert "." in name, f"能力名应为 '<域>.<动作>' 形式: {name}"


def test_get_unknown_capability_raises():
    with pytest.raises(LookupError):
        capabilities.get("nope.does_not_exist")


def test_every_capability_declares_an_input_model():
    for cap in capabilities.all_capabilities():
        assert cap.input_model is not None, cap.name
        # pydantic 模型才能自动出 JSON Schema,供 AI 工具层投影。
        assert hasattr(cap.input_model, "model_json_schema"), cap.name


def test_permission_authz_declares_a_permission():
    for cap in capabilities.all_capabilities():
        if cap.authz is Authz.PERMISSION:
            assert cap.permission is not None, cap.name
        else:
            assert cap.permission is None, f"{cap.name}: 非 PERMISSION 鉴权不应声明 permission"


def test_ungated_capabilities_are_exactly_the_allowlist():
    """authz=NONE 的能力必须在白名单里,且白名单不许有多余条目。

    集合相等(而非包含)是关键:新增一个漏权限的能力会失败,
    修好某个已知缺口后忘了摘白名单也会失败。
    """
    ungated = {cap.name for cap in capabilities.all_capabilities() if cap.authz is Authz.NONE}
    assert ungated == set(UNGATED_ALLOWLIST)


def test_custom_authz_capabilities_do_their_own_checks():
    """CUSTOM 要么覆写 authorize,要么在 execute 里逐条判 —— 总之不能是默认实现配空 permission。"""
    for cap in capabilities.all_capabilities():
        if cap.authz is Authz.CUSTOM:
            assert cap.name not in UNGATED_ALLOWLIST, cap.name


def test_subject_scoped_capabilities_are_gated_or_allowlisted():
    for cap in capabilities.all_capabilities():
        if cap.scope is Scope.SUBJECT and cap.authz is Authz.NONE:
            assert cap.name in UNGATED_ALLOWLIST, cap.name


@pytest.mark.parametrize(
    "error, expected",
    [
        (NotFound("x"), 404),
        (Forbidden("x"), 403),
        (Invalid("x"), 400),
        (Conflict("x"), 409),
        (Unprocessable("x"), 422),
    ],
)
def test_domain_error_status_mapping(error, expected):
    assert status_for(error) == expected


def test_unmapped_domain_error_falls_back_to_500():
    class Weird(DomainError):
        pass

    assert status_for(Weird("x")) == 500
