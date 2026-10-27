"""请求语言:从 Accept-Language 解析界面语言,经 ContextVar 在整条调用链上可读。

前端 ``plugins/api.ts`` 给每个请求统一带上 ``Accept-Language``,中间件在这里解析一次,
业务代码(AI 提示词等)用 ``get_locale()`` 读取,不必逐层传参。
后台 worker 没有请求,执行任务前用任务上存的 locale 调用 ``set_locale()``。
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

SUPPORTED_LOCALES = ("zh-CN", "en-US")
DEFAULT_LOCALE = "zh-CN"

# 提示词里用来称呼目标语言的名字。
LANGUAGE_NAMES = {
    "zh-CN": "Simplified Chinese (简体中文)",
    "en-US": "English",
}

_current_locale: ContextVar[str] = ContextVar("current_locale", default=DEFAULT_LOCALE)


def normalize_locale(value: Optional[str]) -> str:
    """把任意语言标签归一到受支持的 locale;不认识时回退默认值。"""
    if not value:
        return DEFAULT_LOCALE
    tag = value.strip().replace("_", "-").lower()
    for supported in SUPPORTED_LOCALES:
        if tag == supported.lower():
            return supported
    primary = tag.split("-", 1)[0]
    for supported in SUPPORTED_LOCALES:
        if primary == supported.split("-", 1)[0].lower():
            return supported
    return DEFAULT_LOCALE


def parse_accept_language(header: Optional[str]) -> str:
    """按 q 值从高到低取第一个受支持的语言;都不支持则返回默认值。"""
    if not header:
        return DEFAULT_LOCALE
    candidates: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        piece = part.strip()
        if not piece:
            continue
        tag, *params = [p.strip() for p in piece.split(";")]
        q = 1.0
        for param in params:
            if param.startswith("q="):
                try:
                    q = float(param[2:])
                except ValueError:
                    q = 0.0
        if q <= 0 or tag == "*":
            continue
        candidates.append((-q, index, tag))
    for _, _, tag in sorted(candidates):
        resolved = normalize_locale(tag)
        primary = tag.replace("_", "-").lower().split("-", 1)[0]
        if primary in {s.split("-", 1)[0].lower() for s in SUPPORTED_LOCALES}:
            return resolved
    return DEFAULT_LOCALE


def get_locale() -> str:
    return _current_locale.get()


def set_locale(value: Optional[str]) -> None:
    _current_locale.set(normalize_locale(value))


def language_name(locale: Optional[str] = None) -> str:
    return LANGUAGE_NAMES[normalize_locale(locale or get_locale())]


class LocaleMiddleware:
    """纯 ASGI 中间件(不用 BaseHTTPMiddleware,避免 ContextVar 在流式响应里丢失)。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            header = None
            for key, value in scope.get("headers", []):
                if key == b"accept-language":
                    header = value.decode("latin-1")
                    break
            _current_locale.set(parse_accept_language(header))
        await self.app(scope, receive, send)
