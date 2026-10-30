"""桌面托盘:迁移失败必须写完整堆栈到日志并弹窗告知,而不是只打一行就悄悄继续启动。"""
import threading

import pytest

from app import channel, tray


def test_migration_failure_logs_traceback_and_shows_dialog(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shown: list = []
    done = threading.Event()

    def fake_message_box(text: str, flags: int = 0) -> int:
        shown.append((text, flags))
        done.set()
        return 0

    def boom(_url: str) -> None:
        raise RuntimeError("(1060, \"Duplicate column name 'stimulus_id'\")")

    monkeypatch.setattr(channel, "message_box", fake_message_box)
    monkeypatch.setattr("app.core.config.is_configured", lambda: True)
    monkeypatch.setattr("app.core.config.get_db_url", lambda: "mysql+aiomysql://x")
    monkeypatch.setattr("app.db.migrations.run_migrations", boom)

    tray._Server()._run_migrations_once()

    assert done.wait(5)
    text, flags = shown[0]
    assert "Duplicate column name 'stimulus_id'" in text
    assert "app.log" in text
    assert flags == channel.MB_ICONERROR

    err = capsys.readouterr().err
    assert "migration failed" in err
    assert "Traceback" in err
