"""Unified desktop launcher.

Two roles, selected automatically:

* **tray** (default for the packaged build): shows a notification-area icon and
  runs the whole app in-process. See ``app.tray``.
* **server**: runs migrations, the background worker and uvicorn in the
  foreground. Used in development (``uv run python run.py``) and by docker.

Force a role with ``--tray`` / ``--server`` or ``QB_ROLE=tray|server``.
"""

import multiprocessing
import os
import sys
import threading
import time
from pathlib import Path

# Ensure ``app`` is importable both in dev and when frozen.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _open_browser(url: str) -> None:
    """Wait for the server to accept connections, then open the UI."""
    import socket
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host, port = parsed.hostname or "127.0.0.1", parsed.port or 80
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                break
        except OSError:
            time.sleep(0.5)
    else:
        return  # server never came up; skip opening

    # Prefer a native window (system WebView) when pywebview is available,
    # otherwise fall back to the default browser.
    try:
        import webview  # type: ignore

        from app.desktop_i18n import display_name, load_saved_preference

        load_saved_preference()
        webview.create_window(display_name(), url, width=1280, height=800)
        webview.start()
    except Exception:
        import webbrowser

        webbrowser.open(url)


def start_worker() -> None:
    from app.tray import ensure_std_streams

    ensure_std_streams()
    from app import worker

    worker.main()


def _offer_preview_seed() -> None:
    """测试版首次启动:询问是否复制一份正式版数据。必须先于任何导入 config 的代码执行。"""
    from app import channel
    from app.desktop_i18n import tr

    if not channel.PREVIEW or os.getenv("DATA_DIR"):
        return
    stable, preview = channel.desktop_data_dir(False), channel.desktop_data_dir(True)
    state = channel.seed_state(stable, preview)
    if state == "available":
        answer = channel.message_box(tr("seed.ask"), channel.MB_YESNO | channel.MB_ICONQUESTION)
        if answer != channel.IDYES:
            channel.decline_seed(preview)
            return
        try:
            channel.seed_from_stable(stable, preview)
        except Exception as exc:  # noqa: BLE001
            channel.message_box(tr("seed.failed", error=exc))
            channel.decline_seed(preview)
    elif state == "mysql":
        channel.message_box(tr("seed.mysql"))
        channel.decline_seed(preview)


def run_server() -> None:
    """Run migrations, the worker and uvicorn in THIS process (foreground)."""
    from app.core.config import get_db_url, is_configured, settings
    from app.db.migrations import run_migrations

    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    host = os.getenv("HOST", "127.0.0.1")
    from app.channel import DEFAULT_PORT

    port = int(os.getenv("PORT", str(DEFAULT_PORT)))
    open_ui = os.getenv("OPEN_UI", "1") != "0"

    # Apply migrations up front when the database is already configured. On a
    # brand-new install this is skipped; the setup wizard migrates on /complete.
    if is_configured():
        try:
            run_migrations(get_db_url())
        except Exception as exc:  # noqa: BLE001
            print(f"[launcher] migration failed: {exc}", file=sys.stderr)

    # Background worker (resilient: it waits internally until configured).
    proc = multiprocessing.Process(target=start_worker, daemon=True)
    proc.start()

    if open_ui:
        threading.Thread(
            target=_open_browser, args=(f"http://{host}:{port}/",), daemon=True
        ).start()

    import uvicorn

    from app.main import app

    uvicorn.run(app, host=host, port=port, log_level=settings.LOG_LEVEL.lower())


def run_tray() -> None:
    from app.tray import run_tray as _run_tray

    _run_tray()


def main() -> None:
    multiprocessing.freeze_support()  # required for frozen Windows builds

    _offer_preview_seed()

    from app.tray import ensure_std_streams

    ensure_std_streams()

    role = os.getenv("QB_ROLE", "").strip().lower()
    if "--server" in sys.argv or role == "server":
        run_server()
    elif "--tray" in sys.argv or role == "tray":
        run_tray()
    elif getattr(sys, "frozen", False):
        run_tray()
    else:
        run_server()


if __name__ == "__main__":
    main()
