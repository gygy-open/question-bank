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

import json
import multiprocessing
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from typing import Callable

from app import channel, macos_login_item
from app.desktop_i18n import display_name, tr

DEFAULT_PORT = int(os.getenv("PORT", str(channel.DEFAULT_PORT)))
_PORT_SCAN = 10  # 默认端口被别的程序占用时,往后最多再试这么多个
# 启动时解析一次:默认端口可能被无关程序占着,此时顺延而不是直接崩在 WinError 10048。
PORT = DEFAULT_PORT
_MUTEX_HANDLE = None
_STREAMS_REDIRECTED = False


def _url() -> str:
    return f"http://127.0.0.1:{PORT}/"


def _port_available(host: str, port: int) -> bool:
    """能否在该地址上监听。刻意不设 SO_REUSEADDR——在 Windows 上那会让探测"成功"在一个已被占用的端口上。"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _instance_responding(port: int) -> bool:
    """该端口上是否已经有一个题库服务在应答。"""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/v1/system/version", timeout=2
        ) as resp:
            data = json.load(resp)
    except Exception:  # noqa: BLE001 - 任何异常都只说明"不是我们"
        return False
    return bool(data.get("version")) and str(data.get("repo", "")).endswith("question-bank")


def _running_instance_port() -> "int | None":
    """已在运行的本应用实例所用端口(含它顺延到的端口),没有则 None。"""
    for port in range(DEFAULT_PORT, DEFAULT_PORT + _PORT_SCAN + 1):
        if not _port_available("127.0.0.1", port) and _instance_responding(port):
            return port
    return None


def _resolve_port(host: str) -> "int | None":
    for port in range(DEFAULT_PORT, DEFAULT_PORT + _PORT_SCAN + 1):
        if _port_available(host, port):
            return port
    return None


def _wait_for_instance(timeout: float = 30.0) -> "int | None":
    deadline = time.time() + timeout
    while time.time() < deadline:
        port = _running_instance_port()
        if port is not None:
            return port
        time.sleep(0.5)
    return None


def _acquire_single_instance() -> bool:
    """Return False if another tray instance already holds the named mutex."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        handle = kernel32.CreateMutexW(None, 0, channel.INSTANCE_MUTEX)
        last_error = ctypes.get_last_error()
        error_already_exists = 183
        if not handle:
            return True  # 创建失败说明判断不了,交给端口探测兜底
        global _MUTEX_HANDLE
        _MUTEX_HANDLE = handle
        return last_error != error_already_exists
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
    ``print()``. A macOS ``.app`` launched from Finder/Dock instead gets
    ``/dev/null``, which silently drops every log line. Redirect both cases to
    a log file under the data dir (or devnull).
    """
    if not _needs_log_redirect():
        return
    mac_bundle = _is_mac_bundle()
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
    global _STREAMS_REDIRECTED
    _STREAMS_REDIRECTED = True
    if sys.stdout is None or mac_bundle:
        sys.stdout = stream
    if sys.stderr is None or mac_bundle:
        sys.stderr = stream


def _is_mac_bundle() -> bool:
    """打包的 macOS 程序且不是从终端启动(从终端运行时日志直接打到终端,方便排查)。"""
    if sys.platform != "darwin" or not getattr(sys, "frozen", False):
        return False
    try:
        return not (sys.stderr is not None and sys.stderr.isatty())
    except (AttributeError, ValueError):
        return True


def _needs_log_redirect() -> bool:
    if _STREAMS_REDIRECTED:
        return False
    return sys.stdout is None or sys.stderr is None or _is_mac_bundle()


def _wait_for_port(
    host: str,
    port: int,
    timeout: float = 30.0,
    alive: "Callable[[], bool] | None" = None,
) -> bool:
    """等端口可连;alive 返回 False(服务线程已退出)时提前放弃。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            if alive is not None and not alive():
                return False
            time.sleep(0.5)
    return False


def _show_start_failed() -> None:
    from app.core.config import settings

    channel.message_box(
        tr("error.start_failed", log=settings.DATA_DIR / "logs" / "app.log"),
        channel.MB_ICONERROR,
    )


def _show_migration_failed(exc: BaseException) -> None:
    """迁移失败仍继续启动,但必须告知用户;对话框会阻塞,放到后台线程以免卡住启动。"""
    from app.core.config import settings

    reason = " ".join(str(exc).split())
    if len(reason) > 300:
        reason = reason[:300] + "…"
    message = tr(
        "error.migration_failed",
        error=reason,
        log=settings.DATA_DIR / "logs" / "app.log",
    )
    threading.Thread(
        target=channel.message_box,
        args=(message, channel.MB_ICONERROR),
        daemon=True,
    ).start()


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


def _firewall_command(enable: bool, program: str, netsh: str = "netsh") -> str:
    """给 cmd /c 用的命令串:一次提权里顺带清掉旧版按端口命名的规则。"""
    base = f"{netsh} advfirewall firewall"
    commands = [
        f'{base} delete rule name="{channel.LEGACY_FIREWALL_RULE}"',
        f'{base} delete rule name="{channel.FIREWALL_RULE}"',
    ]
    if enable:
        # 按程序放行而非按端口:端口可能顺延,规则不该跟着失效。
        commands.append(
            f'{base} add rule name="{channel.FIREWALL_RULE}" '
            f'dir=in action=allow protocol=TCP program="{program}" enable=yes'
        )
    return " & ".join(commands)


def _set_firewall_rule(enable: bool) -> None:
    """Add/remove the inbound firewall rule (Windows only; one UAC prompt per toggle)."""
    if os.name != "nt":
        return
    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    command = _firewall_command(enable, sys.executable, os.path.join(system32, "netsh.exe"))
    try:
        import ctypes

        ctypes.windll.shell32.ShellExecuteW(
            None, "runas", os.path.join(system32, "cmd.exe"), f"/c {command}", None, 0
        )
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
                print("[tray] migration failed:", file=sys.stderr)
                traceback.print_exc()
                _show_migration_failed(exc)

    def start(self, lan: bool) -> None:
        import uvicorn

        from app.core.config import settings
        from app.main import app
        from app.services import mdns

        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._run_migrations_once()

        if self._worker is None or not self._worker.is_alive():
            self._worker = multiprocessing.Process(target=_start_worker, daemon=True)
            self._worker.start()

        host = "0.0.0.0" if lan else "127.0.0.1"
        if lan:
            mdns.start(_lan_ip(), PORT)
        else:
            mdns.stop()
        config = uvicorn.Config(
            app, host=host, port=PORT, log_level=settings.LOG_LEVEL.lower()
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        from app.services import mdns

        mdns.stop()
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)
        self._server = None
        self._thread = None

    def restart(self, lan: bool) -> None:
        self.stop()
        self.start(lan)

    def shutdown(self) -> None:
        """Stop the server AND the worker, for exits that skip Python's atexit hooks.

        macOS ``-[NSApplication terminate:]`` (⌘Q, Dock "Quit", logout) ends the
        process with C ``exit()``, so multiprocessing never reaps daemon children.
        """
        self.stop()
        worker, self._worker = self._worker, None
        if worker is not None and worker.is_alive():
            worker.terminate()
            worker.join(timeout=5)


def _toggle_login_item(icon, notify: Callable[[str], None]) -> None:
    """菜单「登录时启动」:切换 macOS 登录项;需要用户在系统设置里批准时打开对应页面。"""
    current = macos_login_item.status()
    if current == macos_login_item.REQUIRES_APPROVAL:
        # 已注册但被用户在系统设置里关掉了,只能由用户在那里重新打开
        macos_login_item.open_system_settings()
        notify(tr("notify.login_item_approval", name=display_name()))
        return
    try:
        new_status = macos_login_item.set_enabled(current != macos_login_item.ENABLED)
    except RuntimeError as exc:
        threading.Thread(
            target=channel.message_box,
            args=(tr("error.login_item_failed", error=exc), channel.MB_ICONERROR),
            daemon=True,
        ).start()
        return
    if new_status == macos_login_item.REQUIRES_APPROVAL:
        macos_login_item.open_system_settings()
        notify(tr("notify.login_item_approval", name=display_name()))
    icon.update_menu()


def _make_image():
    """Generate the tray icon at runtime (no bundled asset needed)."""
    from app.branding import make_icon

    return make_icon(64)


def run_tray() -> None:
    global PORT

    import pystray
    from pystray import Menu, MenuItem

    from app import desktop_i18n
    from app.core.config import get_lan_share, set_lan_share

    ensure_std_streams()
    desktop_i18n.load_saved_preference()

    # Bring the existing instance's UI forward instead of starting a second one.
    # 端口是机器级的唯一资源,互斥量只到会话级(快速用户切换/多用户登录各有一份)。
    running = _running_instance_port()
    if running is not None:
        webbrowser.open(f"http://127.0.0.1:{running}/")
        return
    if not _acquire_single_instance():
        # 另一实例刚启动还没监听,等它起来后按它实际的端口打开
        running = _wait_for_instance()
        if running is not None:
            webbrowser.open(f"http://127.0.0.1:{running}/")
        return

    lan = get_lan_share()
    port = _resolve_port("0.0.0.0" if lan else "127.0.0.1")
    if port is None:
        channel.message_box(
            tr("error.ports_busy", first=DEFAULT_PORT, last=DEFAULT_PORT + _PORT_SCAN),
            channel.MB_ICONERROR,
        )
        return
    if port != DEFAULT_PORT:
        channel.message_box(tr("info.port_fallback", default=DEFAULT_PORT, port=port))
    PORT = port

    server = _Server()
    # 迁移、导入应用和启动 uvicorn 都很慢(首次启动尤甚),放到后台线程,先让托盘图标和提示出现。
    ready = threading.Event()
    quitting = threading.Event()

    def _title() -> str:
        return display_name() if ready.is_set() else tr("tray.starting", name=display_name())

    icon = pystray.Icon("question-bank", _make_image(), _title())

    def _notify(message: str) -> None:
        try:
            icon.notify(message, display_name())
        except Exception:  # noqa: BLE001 - notifications are best-effort
            pass

    def _boot() -> None:
        try:
            server.start(lan)
            # 首次启动(解压、杀毒扫描、全量迁移)可能很慢,所以给足时间;服务线程崩溃则立刻放弃。
            started = _wait_for_port("127.0.0.1", PORT, timeout=300, alive=server.is_alive)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            started = False
        if quitting.is_set():
            return
        if not started:
            _show_start_failed()
            icon.stop()
            return
        ready.set()
        icon.title = _title()
        channel.close_splash()
        webbrowser.open(_url())

    def _setup(_icon) -> None:
        icon.visible = True
        _notify(tr("notify.starting"))
        threading.Thread(target=_boot, daemon=True).start()

    def on_open(_icon, _item) -> None:
        if not ready.is_set():
            _notify(tr("notify.still_starting"))
            return
        webbrowser.open(_url())

    def on_toggle_lan(_icon, _item) -> None:
        from app.services import mdns

        if not ready.is_set():
            _notify(tr("notify.still_starting"))
            return
        enabled = not get_lan_share()
        set_lan_share(enabled)
        _set_firewall_rule(enabled)
        server.restart(enabled)
        icon.update_menu()
        if enabled:
            hostname = mdns.current_hostname()
            url = f"http://{_lan_ip()}:{PORT}/"
            if hostname:
                _notify(tr("notify.lan_on_with_host", url=url, host_url=f"http://{hostname}:{PORT}/"))
            else:
                _notify(tr("notify.lan_on", url=url))
        else:
            _notify(tr("notify.lan_off"))

    def on_restart(_icon, _item) -> None:
        if not ready.is_set():
            _notify(tr("notify.still_starting"))
            return
        server.restart(get_lan_share())
        _notify(tr("notify.restarted"))

    def on_quit(_icon, _item) -> None:
        quitting.set()
        server.stop()
        icon.stop()

    # 文字用 callable:网页端切换语言后 update_menu() 即可刷新,无需重启托盘。
    items = [
        MenuItem(lambda _i: tr("menu.open"), on_open, default=True),
        MenuItem(lambda _i: tr("menu.lan_share"), on_toggle_lan, checked=lambda _i: get_lan_share()),
    ]
    if macos_login_item.is_supported():
        items.append(
            MenuItem(
                lambda _i: tr("menu.launch_at_login"),
                lambda _icon, _item: _toggle_login_item(icon, _notify),
                checked=lambda _i: macos_login_item.is_enabled(),
            )
        )
    items += [
        MenuItem(lambda _i: tr("menu.restart"), on_restart),
        MenuItem(lambda _i: tr("menu.quit"), on_quit),
    ]
    icon.menu = Menu(*items)

    def _on_locale_change() -> None:
        icon.title = _title()
        icon.update_menu()

    desktop_i18n.on_change(_on_locale_change)

    if sys.platform == "darwin":
        from app import macos_dock

        def _on_terminate() -> None:
            quitting.set()
            server.shutdown()

        macos_dock.install(
            on_open=lambda: on_open(icon, None),
            on_terminate=_on_terminate,
            open_title=lambda: tr("menu.open"),
            quit_title=lambda: tr("menu.quit_app", name=display_name()),
        )
        desktop_i18n.on_change(macos_dock.refresh)

    icon.run(setup=_setup)
