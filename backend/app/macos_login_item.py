"""macOS「登录时启动」:用 ``SMAppService.mainAppService``(macOS 13+)把 .app 本身注册为登录项。

与「系统设置 → 通用 → 登录项」是同一份状态:用户在那里增删,这里读到的状态也随之变化;.app 被移动后
依然有效,删除 .app 后自然失效。只有打包后的 .app 才能注册(开发环境里 status 为 NotFound,菜单不显示)。
"""
from __future__ import annotations

import sys

NOT_REGISTERED = 0
ENABLED = 1
REQUIRES_APPROVAL = 2  # 已注册,但用户在系统设置里关掉了(或系统要求用户批准)
NOT_FOUND = 3


def _service():
    from ServiceManagement import SMAppService  # type: ignore

    return SMAppService.mainAppService()


def status() -> int:
    try:
        return int(_service().status())
    except Exception:  # noqa: BLE001
        return NOT_FOUND


def is_supported() -> bool:
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return False
    try:
        _service()
    except Exception:  # noqa: BLE001
        return False
    return True


def is_enabled() -> bool:
    return status() == ENABLED


def set_enabled(enabled: bool) -> int:
    """注册/取消登录项,返回之后的状态;失败时抛出 ``RuntimeError``(带系统给出的原因)。"""
    service = _service()
    if enabled:
        ok, error = service.registerAndReturnError_(None)
    else:
        ok, error = service.unregisterAndReturnError_(None)
    if not ok:
        reason = error.localizedDescription() if error is not None else "unknown error"
        raise RuntimeError(str(reason))
    return status()


def open_system_settings() -> None:
    try:
        from ServiceManagement import SMAppService  # type: ignore

        SMAppService.openSystemSettingsLoginItems()
    except Exception:  # noqa: BLE001
        pass
