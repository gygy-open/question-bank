"""桌面外壳文案:两种语言的 key/占位符一致,语言来源的优先级,以及网页端切换语言的接口。"""
import json
import re
import string
from typing import Iterator, Set

import pytest
from httpx import ASGITransport, AsyncClient

from app import desktop_i18n
from app.core.config import settings


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(desktop_i18n, "_preferred", None)
    monkeypatch.setattr(desktop_i18n, "_listeners", [])
    monkeypatch.setattr(desktop_i18n, "installer_locale", lambda: None)
    monkeypatch.setattr(desktop_i18n, "system_locale", lambda: None)
    yield


def _placeholders(message: str) -> Set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(message) if name}


def test_locales_have_same_keys_and_placeholders() -> None:
    assert set(desktop_i18n.MESSAGES) == set(desktop_i18n.SUPPORTED)
    source = desktop_i18n.MESSAGES[desktop_i18n.FALLBACK]
    for locale, messages in desktop_i18n.MESSAGES.items():
        assert set(messages) == set(source), locale
        for key, message in messages.items():
            assert _placeholders(message) == _placeholders(source[key]), (locale, key)


def test_english_has_no_chinese() -> None:
    for key, message in desktop_i18n.MESSAGES["en-US"].items():
        assert not re.search(r"[\u4e00-\u9fff]", message), key


@pytest.mark.parametrize(
    ("tag", "expected"),
    [("zh", "zh-CN"), ("zh-Hans-CN", "zh-CN"), ("zh_TW", "zh-CN"), ("en", "en-US"), ("EN_gb", "en-US"),
     ("fr-FR", None), ("", None), (None, None), (42, None)],
)
def test_normalize(tag: object, expected: object) -> None:
    assert desktop_i18n.normalize(tag) == expected


def test_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    assert desktop_i18n.current_locale() == desktop_i18n.FALLBACK
    monkeypatch.setattr(desktop_i18n, "system_locale", lambda: "en-US")
    assert desktop_i18n.current_locale() == "en-US"
    monkeypatch.setattr(desktop_i18n, "installer_locale", lambda: "zh-CN")
    assert desktop_i18n.current_locale() == "zh-CN"
    desktop_i18n.set_preferred("en")
    assert desktop_i18n.current_locale() == "en-US"
    assert desktop_i18n.tr("menu.quit") == "Quit"


def test_tr_formats_and_falls_back() -> None:
    desktop_i18n.set_preferred("en-US")
    assert desktop_i18n.tr("info.port_fallback", default=8000, port=8001) == (
        "Port 8000 is in use by another program; using 8001 this time."
    )
    assert desktop_i18n.tr("no.such.key") == "no.such.key"


def test_listeners_only_fire_on_change() -> None:
    calls = []
    desktop_i18n.on_change(lambda: calls.append(desktop_i18n.current_locale()))
    desktop_i18n.set_preferred("en-US")
    desktop_i18n.set_preferred("en")
    assert desktop_i18n.set_preferred("fr") is None
    desktop_i18n.set_preferred("zh-CN")
    assert calls == ["en-US", "zh-CN"]


def test_saved_preference_round_trip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    (tmp_path / "config.json").write_text(json.dumps({"lan_share": True}), encoding="utf-8")
    assert desktop_i18n.save_preference("en") == "en-US"
    saved = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert saved == {"lan_share": True, desktop_i18n.CONFIG_KEY: "en-US"}

    desktop_i18n.set_preferred("zh-CN")
    desktop_i18n.load_saved_preference()
    assert desktop_i18n.current_locale() == "en-US"


async def _put_locale(client_host: str, locale: str) -> dict:
    from app.main import app

    transport = ASGITransport(app=app, client=(client_host, 50000))
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.put("/api/v1/system/desktop-locale", json={"locale": locale})
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_endpoint_applies_local_requests(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    assert await _put_locale("127.0.0.1", "en-US") == {"applied": True, "locale": "en-US"}
    assert desktop_i18n.current_locale() == "en-US"
    assert await _put_locale("::1", "ja-JP") == {"applied": False, "locale": None}
    assert desktop_i18n.current_locale() == "en-US"


@pytest.mark.asyncio
async def test_endpoint_ignores_lan_clients(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    assert await _put_locale("192.168.1.20", "en-US") == {"applied": False, "locale": None}
    assert desktop_i18n.current_locale() == desktop_i18n.FALLBACK
    assert not (tmp_path / "config.json").exists()
