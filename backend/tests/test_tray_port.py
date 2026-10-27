"""桌面版端口冲突处理:默认端口被占用时要么认出是自己,要么顺延,不能崩在 WinError 10048。"""
import json
import socket
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import tray

_OUR_VERSION = {"version": "1.5.0", "repo": "gygy-open/question-bank"}


def _free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


@contextmanager
def _occupied(port: int):
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        yield
    finally:
        sock.close()


@contextmanager
def _http_server(port: int, payload: dict):
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # 别污染测试输出
            pass

    server = HTTPServer(("127.0.0.1", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def default_port(monkeypatch) -> int:
    port = _free_port()
    monkeypatch.setattr(tray, "DEFAULT_PORT", port)
    monkeypatch.setattr(tray, "PORT", port)
    return port


def test_resolve_port_skips_a_port_held_by_another_program(default_port):
    with _occupied(default_port):
        assert tray._resolve_port("127.0.0.1") == default_port + 1
    assert tray._resolve_port("127.0.0.1") == default_port


def test_running_instance_is_recognised_only_by_our_own_api(default_port):
    assert tray._running_instance_port() is None

    with _http_server(default_port, {"name": "some other app"}):
        assert tray._running_instance_port() is None

    with _http_server(default_port, _OUR_VERSION):
        assert tray._running_instance_port() == default_port


def test_firewall_rule_follows_program_not_port_and_cleans_legacy_rule():
    exe = r"C:\Program Files\QuestionBank\question-bank.exe"
    enable = tray._firewall_command(True, exe).split(" & ")
    assert enable[0].endswith(f'delete rule name="{tray.channel.LEGACY_FIREWALL_RULE}"')
    assert enable[1].endswith(f'delete rule name="{tray.channel.FIREWALL_RULE}"')
    assert f'program="{exe}"' in enable[2] and "localport" not in enable[2]

    assert tray._firewall_command(False, exe).split(" & ") == enable[:2]


def test_wait_for_port_gives_up_when_server_thread_died(default_port):
    start = time.time()
    assert tray._wait_for_port("127.0.0.1", default_port, timeout=30, alive=lambda: False) is False
    assert time.time() - start < 5
