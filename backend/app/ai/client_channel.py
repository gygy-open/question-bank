"""前端工具的等待/回传通道。

**这是仓库里第一个跨请求的内存注册表** —— 现有的异步交接(导入任务)一律是「写一行 +
前端轮询」。这里刻意不那么做:等待方是同一个进程里正在跑的协程(SSE 生成器),不是游离
的后台任务,用 DB 行 + 轮询只会平添延迟和写放大,而且 run 结束后那行还得清理。

成立的前提是**单进程**:server 角色的 `uvicorn.run(app, ...)` 传的是 app 对象(workers>1
会直接退出),tray 角色是单进程里的后台线程,Docker 的 `fastapi run` 默认 1 worker 且没有
负载均衡。唯一的破坏方式是设 `WEB_CONCURRENCY>1`,由 `is_enabled()` 挡掉。

因为 SPA 路由跳转不会中断 fetch(chat 流在模块作用域、没有 AbortController),
「先导航、再回报」在同一个 SSE 连接里就能走完,不需要 run 状态持久化或跨页面 resume。
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 等待前端执行的上限。远低于 nginx 的 proxy_read_timeout(600s),
# 所以等待期间不需要发 SSE keepalive 帧。
DEFAULT_TIMEOUT_S = 30.0


@dataclass
class _Pending:
    run_id: str
    future: "asyncio.Future[Dict[str, Any]]"


_PENDING: Dict[str, _Pending] = {}


def is_enabled() -> bool:
    """多进程下本通道会静默失效(回传落到别的 worker),此时直接不提供前端工具。"""
    try:
        workers = int(os.environ.get("WEB_CONCURRENCY", "1"))
    except ValueError:
        workers = 1
    return workers <= 1


def open_ticket(run_id: str) -> str:
    """登记一次等待,返回一次性票据。"""
    ticket = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    _PENDING[ticket] = _Pending(run_id=run_id, future=loop.create_future())
    return ticket


def resolve(ticket: str, run_id: str, payload: Dict[str, Any]) -> bool:
    """前端回传结果。票据不属于该 run、不存在或已被兑现时返回 False。

    刻意**不**在这里摘掉条目:回传可能早于等待方进入 `wait_for`(生成器 yield 出事件后
    要等消费者再驱动一次才会开始等待),提前摘掉会让那次回传丢失、白等一个超时。
    条目统一由 `wait_for` 的 finally 回收,一次性语义靠 future 是否已兑现来保证。
    """
    pending = _PENDING.get(ticket)
    if pending is None or pending.run_id != run_id or pending.future.done():
        return False
    pending.future.set_result(payload)
    return True


async def wait_for(ticket: str, *, timeout: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """等前端回传;超时返回 None(由调用方转成给模型的错误结果,不能挂死)。"""
    pending = _PENDING.get(ticket)
    if pending is None:
        return None
    try:
        return await asyncio.wait_for(
            asyncio.shield(pending.future),
            timeout=DEFAULT_TIMEOUT_S if timeout is None else timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Client tool ticket timed out: %s", ticket)
        return None
    finally:
        # 无论兑现、超时还是被取消(客户端断连)都要清掉,否则条目会永久泄漏。
        _PENDING.pop(ticket, None)


def pending_count() -> int:
    return len(_PENDING)
