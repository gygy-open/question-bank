"""System-tray launcher for the packaged desktop build.

Runs the whole application in-process (migrations + background worker +
uvicorn) and shows a notification-area icon so the user can open the UI,
toggle local-network sharing, restart or quit. This replaces the old
Windows-service deployment: it uses the familiar tray-app mental model
(like most chat / proxy clients) and requires no admin service management.

Local-network sharing is OFF by default. Enabling it rebinds the server to
``0.0.0.0`` and adds a Windows Firewall rule (one UAC prompt); disabling it
rebinds to ``127.0.0.1`` and removes the rule. The secret key is always a
persisted random value (see ``app.core.config``), so exposing the app on the
LAN does not fall back to an insecure default.
"""

import multiprocessing
import os
import socket
import sys
import threading
import time
import webbrowser

PORT = int(os.getenv("PORT", "8000"))
URL_LOCAL = f"http://127.0.0.1:{PORT}/"
_FIREWALL_RULE = f"Question Bank ({PORT})"
_MUTEX_HANDLE = None


def _acquire_single_instance() -> bool:
    """Return False if another tray instance already holds the named mutex."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, "Global\\QuestionBankTray")
        error_already_exists = 183
        if kernel32.GetLastError() == error_already_exists:
            return False
        global _MUTEX_HANDLE
        _MUTEX_HANDLE = handle
        return True
    except Exception:  # noqa: BLE001
        return True


def _start_worker() -> None:
    """Top-level target so it is picklable for the spawn start method."""
    ensure_std_streams()
    from app import worker

    worker.main()


def ensure_std_streams() -> None:
    """Give the windowed build usable stdout/stderr.

    A frozen ``console=False`` build has ``sys.stdout``/``sys.stderr`` set to
    ``None``, which crashes uvicorn's log formatter (``isatty``) and any
    ``print()``. Redirect them to a log file under the data dir (or devnull).
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    stream = None
    try:
        from app.core.config import settings

        log_dir = settings.DATA_DIR / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stream = open(log_dir / "app.log", "a", encoding="utf-8", buffering=1)
    except Exception:  # noqa: BLE001
        try:
            stream = open(os.devnull, "w")
        except OSError:
            return
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def _wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def _open_when_ready(url: str) -> None:
    if _wait_for_port("127.0.0.1", PORT):
        webbrowser.open(url)


def _lan_ip() -> str:
    """Best-effort primary LAN IPv4 address (no packets are actually sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


def _set_firewall_rule(enable: bool) -> None:
    """Add/remove an inbound firewall rule for the server port (Windows only).

    Uses an elevated, hidden ``netsh`` call (one UAC prompt per toggle).
    """
    if os.name != "nt":
        return
    if enable:
        args = (
            f'advfirewall firewall add rule name="{_FIREWALL_RULE}" '
            f"dir=in action=allow protocol=TCP localport={PORT}"
        )
    else:
        args = f'advfirewall firewall delete rule name="{_FIREWALL_RULE}"'
    try:
        import ctypes

        ctypes.windll.shell32.ShellExecuteW(None, "runas", "netsh", args, None, 0)
    except Exception:  # noqa: BLE001 - firewall is best-effort
        pass


class _Server:
    """Runs uvicorn in a background thread; can rebind the host on restart."""

    def __init__(self) -> None:
        self._server = None
        self._thread: "threading.Thread | None" = None
        self._worker: "multiprocessing.Process | None" = None

    def _run_migrations_once(self) -> None:
        from app.core.config import get_db_url, is_configured
        from app.db.migrations import run_migrations

        if is_configured():
            try:
                run_migrations(get_db_url())
            except Exception as exc:  # noqa: BLE001
                print(f"[tray] migration failed: {exc}", file=sys.stderr)

    def start(self, lan: bool) -> None:
        import uvicorn

        from app.core.config import settings
        from app.main import app

        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._run_migrations_once()

        if self._worker is None or not self._worker.is_alive():
            self._worker = multiprocessing.Process(target=_start_worker, daemon=True)
            self._worker.start()

        host = "0.0.0.0" if lan else "127.0.0.1"
        config = uvicorn.Config(
            app, host=host, port=PORT, log_level=settings.LOG_LEVEL.lower()
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._server = None
        self._thread = None

    def restart(self, lan: bool) -> None:
        self.stop()
        self.start(lan)


def _make_image():
    """Generate the tray icon at runtime (no bundled asset needed)."""
    from app.branding import make_icon

    return make_icon(64)


def run_tray() -> None:
    import pystray
    from pystray import Menu, MenuItem

    from app.core.config import get_lan_share, set_lan_share

    ensure_std_streams()

    # Bring the existing instance's UI forward instead of starting a second one.
    if not _acquire_single_instance():
        webbrowser.open(URL_LOCAL)
        return

    server = _Server()
    server.start(get_lan_share())

    # Auto-open the UI once on launch.
    threading.Thread(target=_open_when_ready, args=(URL_LOCAL,), daemon=True).start()

    icon = pystray.Icon("question-bank", _make_image(), "Question Bank")

    def _notify(message: str) -> None:
        try:
            icon.notify(message, "Question Bank")
        except Exception:  # noqa: BLE001 - notifications are best-effort
            pass

    def on_open(_icon, _item) -> None:
        webbrowser.open(URL_LOCAL)

    def on_toggle_lan(_icon, _item) -> None:
        enabled = not get_lan_share()
        set_lan_share(enabled)
        _set_firewall_rule(enabled)
        server.restart(enabled)
        icon.update_menu()
        if enabled:
            _notify(f"局域网共享已开启\nhttp://{_lan_ip()}:{PORT}/")
        else:
            _notify("局域网共享已关闭")

    def on_restart(_icon, _item) -> None:
        server.restart(get_lan_share())
        _notify("已重启")

    def on_quit(_icon, _item) -> None:
        server.stop()
        icon.stop()

    icon.menu = Menu(
        MenuItem("打开题库", on_open, default=True),
        MenuItem("局域网共享", on_toggle_lan, checked=lambda _i: get_lan_share()),
        MenuItem("重启", on_restart),
        MenuItem("退出", on_quit),
    )
    icon.run()
