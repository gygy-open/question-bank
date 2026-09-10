"""前端工具通道:等待、回传、超时与票据安全。

这是仓库里第一个跨请求的内存注册表,所以它的失效模式(超时挂死、票据泄漏、越权回传)
必须有测试兜住。
"""
import asyncio

import pytest

from app.ai import client_channel
from app.ai.contracts import ToolResult
from app.ai.runtime import _client_tool_result


@pytest.fixture(autouse=True)
def _clean_registry():
    client_channel._PENDING.clear()
    yield
    client_channel._PENDING.clear()


async def test_resolve_wakes_the_waiter():
    ticket = client_channel.open_ticket("run-1")

    async def _reply():
        await asyncio.sleep(0)
        assert client_channel.resolve(ticket, "run-1", {"ok": True, "content": "已跳转"})

    _, payload = await asyncio.gather(_reply(), client_channel.wait_for(ticket, timeout=2))
    assert payload["content"] == "已跳转"


async def test_reply_arriving_before_the_wait_is_not_lost():
    """生成器 yield 出事件后要等消费者再驱动一次才开始等待,回传可能先到。

    早期实现在 resolve 里就摘掉了条目,导致这种情况下 wait_for 找不到票据、
    白等一个完整超时 —— 而这正是「导航很快就完成」的常见路径。
    """
    ticket = client_channel.open_ticket("run-1")
    assert client_channel.resolve(ticket, "run-1", {"ok": True, "content": "已打开"})
    assert (await client_channel.wait_for(ticket, timeout=0.05))["content"] == "已打开"
    assert client_channel.pending_count() == 0


async def test_ticket_is_single_use():
    ticket = client_channel.open_ticket("run-1")
    assert client_channel.resolve(ticket, "run-1", {"ok": True})
    # 重复回传拿不到第二次机会。
    assert client_channel.resolve(ticket, "run-1", {"ok": True}) is False
    await client_channel.wait_for(ticket, timeout=0.05)
    assert client_channel.resolve(ticket, "run-1", {"ok": True}) is False


async def test_resolve_rejects_a_foreign_run():
    """票据不可猜,但仍不能让别的 run 兑现它。"""
    ticket = client_channel.open_ticket("run-1")
    assert client_channel.resolve(ticket, "run-2", {"ok": True}) is False
    assert client_channel.pending_count() == 1


def test_resolve_rejects_unknown_ticket():
    assert client_channel.resolve("nope", "run-1", {"ok": True}) is False


async def test_timeout_returns_none_and_reaps_the_entry():
    """超时必须放行 run,并且不能留下永久泄漏的条目。"""
    ticket = client_channel.open_ticket("run-1")
    assert await client_channel.wait_for(ticket, timeout=0.01) is None
    assert client_channel.pending_count() == 0


async def test_cancelled_wait_is_reaped():
    """客户端断连导致生成器被取消时,条目同样要清掉。"""
    ticket = client_channel.open_ticket("run-1")
    task = asyncio.create_task(client_channel.wait_for(ticket, timeout=30))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert client_channel.pending_count() == 0


# --------------------------------------------------------------------------- #
# 结果转换
# --------------------------------------------------------------------------- #
def test_timeout_is_explained_to_the_model():
    result = _client_tool_result(None)
    assert isinstance(result, ToolResult)
    assert "不要重试" in result.content


def test_client_failure_is_passed_through():
    result = _client_tool_result({"ok": False, "content": "路由不存在"})
    assert result.content == "路由不存在"


def test_client_success_carries_data():
    result = _client_tool_result({"ok": True, "content": "已打开", "data": {"path": "/x"}})
    assert result.content == "已打开"
    assert result.data == {"path": "/x"}


# --------------------------------------------------------------------------- #
# 部署护栏
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "value, enabled",
    [(None, True), ("1", True), ("2", False), ("8", False), ("garbage", True)],
)
def test_multi_worker_disables_the_channel(monkeypatch, value, enabled):
    """WEB_CONCURRENCY>1 会静默把回传路由到别的进程,此时必须不提供前端工具。"""
    monkeypatch.delenv("WEB_CONCURRENCY", raising=False)
    if value is not None:
        monkeypatch.setenv("WEB_CONCURRENCY", value)
    assert client_channel.is_enabled() is enabled
