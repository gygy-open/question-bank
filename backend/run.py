"""Unified desktop launcher.

Starts the whole application as a single process tree:

1. Runs pending database migrations (only once configured).
2. Spawns the background import worker as a child process.
3. Opens the default browser (or a native window) at the local server.
4. Serves the FastAPI app (which also hosts the built Nuxt SPA).

Designed to be the PyInstaller entry point, but also runnable in dev with
``uv run python run.py``.
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

        webview.create_window("Question Bank", url, width=1280, height=800)
        webview.start()
    except Exception:
        import webbrowser

        webbrowser.open(url)


def start_worker() -> None:
    from app import worker

    worker.main()


def main() -> None:
    multiprocessing.freeze_support()  # required for frozen Windows builds

    from app.core.config import get_db_url, is_configured, settings
    from app.db.migrations import run_migrations

    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
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

    uvicorn.run("app.main:app", host=host, port=port, log_level=settings.LOG_LEVEL.lower())


if __name__ == "__main__":
    main()
