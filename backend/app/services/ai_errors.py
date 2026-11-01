"""AI 调用错误的分类与重试。

导入队列按类别处理 AI 错误:
- transient:限流、5xx、超时、连接失败 —— 先自动重试;重试后仍失败按服务故障处理。
- provider:额度耗尽、Key 无效、模型不存在、未配置模型 —— 暂停使用同一服务商的任务。
- document:内容过长、输出被截断、模型输出无法解析 —— 只让当前任务失败。
- unknown:无法判断;由调用方结合连续失败次数决定是否升级为服务故障。
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, Optional, TypeVar

from app.models.import_task import ImportPauseReason

logger = logging.getLogger(__name__)

Category = Literal["transient", "provider", "document", "unknown"]
T = TypeVar("T")

RETRY_ATTEMPTS = 3
_BASE_DELAY_SECONDS = 2.0
_MAX_DELAY_SECONDS = 60.0

_QUOTA_HINT = re.compile(r"insufficient[_ ]quota|quota|balance|billing|credit|余额|欠费", re.I)
_KEY_HINT = re.compile(r"api[_ ]?key|unauthori[sz]ed|authentication|permission", re.I)
_MODEL_HINT = re.compile(r"model.*(not[_ ]found|does not exist|not exist|unsupported|invalid)|no such model", re.I)


@dataclass(frozen=True)
class AIErrorKind:
    category: Category
    # provider 类为暂停原因;transient 类为重试耗尽后升级使用的原因。
    reason: Optional[ImportPauseReason] = None
    retry_after: Optional[float] = None


def _status_code(exc: BaseException) -> Optional[int]:
    for attr in ("status_code", "code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int) and 100 <= value < 600:
            return value
    return None


def _error_code(exc: BaseException) -> str:
    """OpenAI 兼容接口的业务错误码(如 insufficient_quota)。"""
    code = getattr(exc, "code", None)
    if isinstance(code, str):
        return code
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        inner = body.get("error") if isinstance(body.get("error"), dict) else body
        value = inner.get("code") or inner.get("type")
        if isinstance(value, str):
            return value
    return ""


def _retry_after(exc: BaseException) -> Optional[float]:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("retry-after")
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_connection_error(exc: BaseException) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, ConnectionError)):
        return True
    try:
        import openai

        if isinstance(exc, openai.APIConnectionError):
            return True
    except ImportError:  # pragma: no cover - openai 是依赖
        pass
    try:
        import httpx

        if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
            return True
    except ImportError:  # pragma: no cover
        pass
    return False


def classify_ai_error(exc: BaseException) -> AIErrorKind:
    from app.capabilities.errors import DomainError
    from app.core.api_errors import ErrorCode
    from app.services.ai_provider import ResponseTruncatedError

    if isinstance(exc, ResponseTruncatedError):
        return AIErrorKind("document")
    if isinstance(exc, DomainError):
        if exc.code == ErrorCode.AI_CONFIG_API_KEY_UNDECRYPTABLE:
            return AIErrorKind("provider", ImportPauseReason.AUTH)
        if str(exc.code or "").startswith("ai_config."):
            return AIErrorKind("provider", ImportPauseReason.MODEL)
        return AIErrorKind("unknown")
    if _is_connection_error(exc):
        return AIErrorKind("transient", ImportPauseReason.UNAVAILABLE)

    status = _status_code(exc)
    if status is None:
        if isinstance(exc, ValueError):
            # JSON/Pydantic 解析失败等:模型对这份文档的输出不可用。
            return AIErrorKind("document")
        return AIErrorKind("unknown")

    message = str(getattr(exc, "message", None) or exc)
    code = _error_code(exc)
    if status == 429:
        if code == "insufficient_quota" or (code and _QUOTA_HINT.search(code)):
            return AIErrorKind("provider", ImportPauseReason.QUOTA)
        # 限流重试后仍失败:按不可达处理,稍后自动再试(额度按天重置的服务也能自行恢复)。
        return AIErrorKind("transient", ImportPauseReason.UNAVAILABLE, _retry_after(exc))
    if status == 402:
        return AIErrorKind("provider", ImportPauseReason.QUOTA)
    if status in (401, 403):
        if _QUOTA_HINT.search(message) and not _KEY_HINT.search(message):
            return AIErrorKind("provider", ImportPauseReason.QUOTA)
        return AIErrorKind("provider", ImportPauseReason.AUTH)
    if status == 404:
        return AIErrorKind("provider", ImportPauseReason.MODEL)
    if status in (408, 409) or status >= 500:
        return AIErrorKind("transient", ImportPauseReason.UNAVAILABLE, _retry_after(exc))
    if status == 400:
        # Gemini 对无效 Key 返回 400 INVALID_ARGUMENT。
        if _KEY_HINT.search(message) and "key" in message.lower():
            return AIErrorKind("provider", ImportPauseReason.AUTH)
        if _MODEL_HINT.search(message):
            return AIErrorKind("provider", ImportPauseReason.MODEL)
        return AIErrorKind("document")
    if 400 <= status < 500:
        return AIErrorKind("document")
    return AIErrorKind("unknown")


def _delay(attempt: int, retry_after: Optional[float]) -> float:
    if retry_after is not None and retry_after >= 0:
        return min(retry_after, _MAX_DELAY_SECONDS)
    backoff = _BASE_DELAY_SECONDS * (2 ** attempt)
    return min(backoff + random.uniform(0, 1), _MAX_DELAY_SECONDS)


async def with_ai_retry(
    call: Callable[[], Awaitable[T]],
    *,
    attempts: int = RETRY_ATTEMPTS,
    sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> T:
    """执行一次 AI 调用;临时故障按退避重试,其余错误立即抛出。"""
    for attempt in range(attempts):
        try:
            return await call()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            kind = classify_ai_error(exc)
            if kind.category != "transient" or attempt == attempts - 1:
                raise
            delay = _delay(attempt, kind.retry_after)
            logger.warning("Transient AI error (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, attempts, delay, exc)
            await sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
