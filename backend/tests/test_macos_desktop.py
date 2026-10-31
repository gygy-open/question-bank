"""macOS 桌面版的平台适配:对话框、应用图标、系统语言。不依赖真实的 AppKit / osascript。"""
import subprocess
import sys
import types
from typing import List

import pytest

from app import branding, channel, desktop_i18n, macos_login_item


@pytest.fixture
def mac(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(desktop_i18n, "_preferred", "en-US")


def _fake_osascript(monkeypatch: pytest.MonkeyPatch, stdout: str, returncode: int = 0) -> List[List[str]]:
    calls: List[List[str]] = []

    def run(args, **_kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_yes_no_dialog_maps_answer(mac, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_osascript(monkeypatch, "Yes\n")
    flags = channel.MB_YESNO | channel.MB_ICONQUESTION
    assert channel.message_box("Copy data?", flags) == channel.IDYES

    args = calls[0]
    assert args[0] == "osascript"
    # 文字只通过 argv 传入,不拼进脚本
    assert "Copy data?" not in args[2]
    assert args[3:] == [desktop_i18n.display_name(), "Copy data?", "Yes", "No"]
    assert "default button 2" in args[2]

    _fake_osascript(monkeypatch, "No\n")
    assert channel.message_box("Copy data?", flags) != channel.IDYES


def test_dialog_cancel_or_failure_is_not_yes(mac, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_osascript(monkeypatch, "", returncode=1)
    assert channel.message_box("x", channel.MB_YESNO) != channel.IDYES


def test_error_dialog_uses_critical_style(mac, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_osascript(monkeypatch, "OK\n")
    assert channel.message_box("boom", channel.MB_ICONERROR) == channel.IDOK
    assert " as critical " in calls[0][2]
    assert "as informational" in channel._mac_alert_script(channel.MB_ICONINFO)


def test_close_splash_is_noop_without_splash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("_PYI_SPLASH_IPC", raising=False)
    monkeypatch.setitem(sys.modules, "pyi_splash", None)  # import would raise if attempted
    channel.close_splash()


def test_app_icon_has_background_plate(tmp_path) -> None:
    img = branding.make_app_icon(256, preview=False)
    assert img.size == (256, 256)
    assert img.getpixel((0, 0))[3] == 0  # transparent margin outside the plate
    assert img.getpixel((40, 128))[:3] == (255, 255, 255)  # white plate

    path = tmp_path / "logo.icns"
    branding.save_icns(str(path), preview=True)
    assert path.read_bytes()[:4] == b"icns"


def test_macos_system_locale_reads_preferred_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    class NSLocale:
        @staticmethod
        def preferredLanguages():  # noqa: N802
            return ["fr-FR", "zh-Hans-CN", "en-US"]

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(desktop_i18n.os, "name", "posix")
    monkeypatch.setitem(sys.modules, "Foundation", types.SimpleNamespace(NSLocale=NSLocale))
    desktop_i18n.system_locale.cache_clear()
    try:
        assert desktop_i18n.system_locale() == "zh-CN"
    finally:
        desktop_i18n.system_locale.cache_clear()


class _FakeError:
    def localizedDescription(self):  # noqa: N802
        return "Operation not permitted"


class _FakeService:
    def __init__(self, status: int, ok: bool = True) -> None:
        self._status = status
        self._ok = ok

    def status(self) -> int:
        return self._status

    def registerAndReturnError_(self, _err):  # noqa: N802
        if not self._ok:
            return False, _FakeError()
        self._status = macos_login_item.ENABLED
        return True, None

    def unregisterAndReturnError_(self, _err):  # noqa: N802
        self._status = macos_login_item.NOT_REGISTERED
        return True, None


def test_login_item_register_and_unregister(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakeService(macos_login_item.NOT_REGISTERED)
    monkeypatch.setattr(macos_login_item, "_service", lambda: service)
    assert not macos_login_item.is_enabled()
    assert macos_login_item.set_enabled(True) == macos_login_item.ENABLED
    assert macos_login_item.is_enabled()
    assert macos_login_item.set_enabled(False) == macos_login_item.NOT_REGISTERED


def test_login_item_error_carries_system_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(macos_login_item, "_service", lambda: _FakeService(0, ok=False))
    with pytest.raises(RuntimeError, match="Operation not permitted"):
        macos_login_item.set_enabled(True)


def test_login_item_unsupported_outside_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert not macos_login_item.is_supported()
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert not macos_login_item.is_supported()


class _Icon:
    def __init__(self) -> None:
        self.updates = 0

    def update_menu(self) -> None:
        self.updates += 1


def _toggle(monkeypatch: pytest.MonkeyPatch, service: _FakeService):
    from app import tray

    opened: List[bool] = []
    notes: List[str] = []
    monkeypatch.setattr(macos_login_item, "_service", lambda: service)
    monkeypatch.setattr(macos_login_item, "open_system_settings", lambda: opened.append(True))
    icon = _Icon()
    tray._toggle_login_item(icon, notes.append)
    return icon, opened, notes


def test_toggle_login_item_flips_state(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakeService(macos_login_item.NOT_REGISTERED)
    icon, opened, notes = _toggle(monkeypatch, service)
    assert service.status() == macos_login_item.ENABLED
    assert icon.updates == 1 and not opened and not notes

    icon, _, _ = _toggle(monkeypatch, service)
    assert service.status() == macos_login_item.NOT_REGISTERED


def test_toggle_login_item_needing_approval_opens_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _FakeService(macos_login_item.REQUIRES_APPROVAL)
    icon, opened, notes = _toggle(monkeypatch, service)
    assert service.status() == macos_login_item.REQUIRES_APPROVAL  # 不能替用户改,只能引导
    assert opened == [True] and len(notes) == 1
