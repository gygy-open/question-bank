"""桌面外壳(托盘、启动对话框、窗口标题)的界面文案。

网页界面的翻译在前端(vue-i18n),这里只管 Python 进程自己弹出的文字。语言按以下顺序决定:

1. 用户在网页里切换的语言(前端调 ``PUT /system/desktop-locale``,存入 config.json);
2. 安装包选择的语言(installer.iss 写入 ``HKLM\\Software\\<AppDir>\\InstallerLanguage``);
3. Windows 界面语言;
4. ``FALLBACK``(与前端的回退语言一致)。

与 ``app.channel`` 一样会在 ``app.core.config`` 之前被使用,模块级不得导入 config。
"""
from __future__ import annotations

import functools
import os
import threading
from typing import Callable, Dict, List, Optional

SUPPORTED = ("zh-CN", "en-US")
FALLBACK = "zh-CN"
CONFIG_KEY = "desktop_locale"
# 与 deploy/windows/installer.iss 的 MyAppDir 保持一致。
_REGISTRY_KEYS = {False: r"Software\QuestionBank", True: r"Software\QuestionBank Preview"}
_REGISTRY_VALUE = "InstallerLanguage"
_LANG_CHINESE = 0x04

MESSAGES: Dict[str, Dict[str, str]] = {
    "zh-CN": {
        "app.name": "QuestionBank",
        "app.name_preview": "QuestionBank 测试版",
        "menu.open": "打开题库",
        "menu.lan_share": "局域网共享",
        "menu.restart": "重启",
        "menu.quit": "退出",
        "notify.lan_on": "局域网共享已开启\n{url}",
        "notify.lan_on_with_host": "局域网共享已开启\n{url} 或 {host_url}",
        "notify.lan_off": "局域网共享已关闭",
        "notify.restarted": "已重启",
        "notify.starting": "正在启动，请稍候…\n首次启动可能需要一两分钟，准备好后会自动打开。",
        "notify.still_starting": "仍在启动中，请稍候…",
        "tray.starting": "{name}（正在启动…）",
        "error.start_failed": "服务未能启动。\n\n请把日志发给我们排查：\n{log}",
        "error.ports_busy": "端口 {first}~{last} 都被其他程序占用，无法启动。\n\n请关闭占用这些端口的程序后重试。",
        "info.port_fallback": "端口 {default} 已被其他程序占用，本次改用 {port}。",
        "seed.ask": (
            "检测到正式版的题库数据。\n\n"
            "是否复制一份到测试版中使用？\n"
            "· 选「是」：测试版使用这份副本，正式版的数据不会被修改。\n"
            "· 选「否」：测试版以全新状态启动。"
        ),
        "seed.failed": "复制正式版数据失败：{error}\n\n测试版将以全新状态启动。",
        "seed.mysql": (
            "正式版使用的是 MySQL 数据库，无法自动复制。\n\n"
            "测试版将以全新状态启动。如需使用正式版数据，请先复制一个数据库，"
            "再在设置向导中连接它；不要连接正式版正在使用的数据库。"
        ),
    },
    "en-US": {
        "app.name": "QuestionBank",
        "app.name_preview": "QuestionBank Preview",
        "menu.open": "Open QuestionBank",
        "menu.lan_share": "LAN sharing",
        "menu.restart": "Restart",
        "menu.quit": "Quit",
        "notify.lan_on": "LAN sharing is on\n{url}",
        "notify.lan_on_with_host": "LAN sharing is on\n{url} or {host_url}",
        "notify.lan_off": "LAN sharing is off",
        "notify.restarted": "Restarted",
        "notify.starting": "Starting, please wait…\nThe first launch can take a minute or two; it will open automatically when ready.",
        "notify.still_starting": "Still starting, please wait…",
        "tray.starting": "{name} (starting…)",
        "error.start_failed": "The service failed to start.\n\nPlease send us the log file:\n{log}",
        "error.ports_busy": (
            "Ports {first}-{last} are all in use by other programs, so QuestionBank cannot start.\n\n"
            "Close the programs using these ports and try again."
        ),
        "info.port_fallback": "Port {default} is in use by another program; using {port} this time.",
        "seed.ask": (
            "Data from the stable version of QuestionBank was found.\n\n"
            "Copy it into the Preview version?\n"
            "· Yes: the Preview uses a copy; the stable version's data is not modified.\n"
            "· No: the Preview starts fresh."
        ),
        "seed.failed": "Failed to copy the stable version's data: {error}\n\nThe Preview will start fresh.",
        "seed.mysql": (
            "The stable version uses a MySQL database, which cannot be copied automatically.\n\n"
            "The Preview will start fresh. To use the stable data, make a copy of the database first "
            "and connect to the copy in the setup wizard; do not connect to the database the stable version is using."
        ),
    },
}

_lock = threading.Lock()
_preferred: Optional[str] = None
_listeners: List[Callable[[], None]] = []


def normalize(tag: object) -> Optional[str]:
    """把 ``zh`` / ``zh-Hans-CN`` / ``en_GB`` 等归到受支持的语言;无法识别返回 None。"""
    if not isinstance(tag, str) or not tag.strip():
        return None
    primary = tag.strip().replace("_", "-").split("-")[0].lower()
    if primary == "zh":
        return "zh-CN"
    if primary == "en":
        return "en-US"
    return None


@functools.lru_cache(maxsize=None)
def installer_locale() -> Optional[str]:
    if os.name != "nt":
        return None
    from app.channel import PREVIEW

    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _REGISTRY_KEYS[PREVIEW]) as key:
            value, _type = winreg.QueryValueEx(key, _REGISTRY_VALUE)
    except OSError:
        return None
    return normalize(value)


@functools.lru_cache(maxsize=None)
def system_locale() -> Optional[str]:
    if os.name == "nt":
        try:
            import ctypes

            langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        except Exception:  # noqa: BLE001
            return None
        return "zh-CN" if langid & 0x3FF == _LANG_CHINESE else "en-US"
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        found = normalize(os.environ.get(var))
        if found:
            return found
    return None


def current_locale() -> str:
    return _preferred or installer_locale() or system_locale() or FALLBACK


def set_preferred(tag: object) -> Optional[str]:
    """设置用户选择的语言并通知托盘刷新;返回归一化后的语言,不支持时返回 None 且不做改动。"""
    global _preferred
    locale = normalize(tag)
    if locale is None:
        return None
    with _lock:
        changed = locale != _preferred
        _preferred = locale
        listeners = list(_listeners)
    if changed:
        for listener in listeners:
            try:
                listener()
            except Exception:  # noqa: BLE001 - 刷新托盘失败不应影响调用方
                pass
    return locale


def load_saved_preference() -> None:
    """从 config.json 读取网页端保存的语言。只能在允许导入 config 之后调用。"""
    from app.core.config import load_runtime_config

    set_preferred(load_runtime_config().get(CONFIG_KEY))


def save_preference(tag: object) -> Optional[str]:
    locale = normalize(tag)
    if locale is None:
        return None
    from app.core.config import save_runtime_config

    save_runtime_config({CONFIG_KEY: locale})
    return set_preferred(locale)


def on_change(listener: Callable[[], None]) -> None:
    with _lock:
        _listeners.append(listener)


def tr(key: str, **params: object) -> str:
    message = MESSAGES.get(current_locale(), {}).get(key) or MESSAGES[FALLBACK].get(key, key)
    return message.format(**params) if params else message


def display_name() -> str:
    from app.channel import PREVIEW

    return tr("app.name_preview" if PREVIEW else "app.name")
