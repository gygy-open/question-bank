"""Agent 运行时 —— 与传输无关的工具循环。

之前这段逻辑焊死在 chat.py 的 SSE generator 里,既没法被 worker / 其他入口复用,
也没法单测。现在它只吐 `AgentEvent`,由适配器负责落到具体传输上。

设计要点:
- 预算是四重的(轮次 / 工具调用数 / 墙钟),不是裸 `for _ in range(5)`。
- 工具失败(含权限被拒)不中断 run:错误文本回喂给模型,让它自我纠正。
- 每一步落 `agent_steps`,排障时能看到模型到底调了什么、拿到了什么。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from app.ai import tools as ai_tools
from app.ai import client_channel
from app.ai.contracts import AgentScene, ToolResult
from app.ai.events import (
    AgentEvent,
    AssistantTurn,
    ClientToolRequested,
    RunFailed,
    RunFinished,
    TextDelta,
    ToolCallFinished,
    ToolCallStarted,
)
from app.capabilities.context import ExecutionContext
from app.models.agent import AgentRun, AgentRunStatus, AgentStep
from app.services.ai_provider import AIProvider, ToolCall

logger = logging.getLogger(__name__)


def _client_tool_result(payload: Optional[Dict[str, Any]]) -> ToolResult:
    """把前端回传(或超时)转成回喂模型的结果。超时不能挂死 run。"""
    if payload is None:
        return ToolResult.text(
            "客户端未在超时时间内响应(用户可能已离开页面)。请不要重试,改为用文字告知用户下一步该怎么做。"
        )
    ok = payload.get("ok", True)
    content = payload.get("content") or ("已完成。" if ok else "客户端执行失败。")
    return ToolResult(content=content, data=payload.get("data"))


@dataclass(frozen=True)
class RunBudget:
    max_turns: int = 5
    max_tool_calls: int = 20
    wall_clock_s: float = 180.0


class AgentRunner:
    def __init__(self, provider: AIProvider, provider_config: Dict[str, Any], budget: RunBudget | None = None):
        self.provider = provider
        self.provider_config = provider_config
        self.budget = budget or RunBudget()

    async def run(
        self,
        ctx: ExecutionContext,
        messages: List[Dict[str, Any]],
        *,
        session_id: Optional[str] = None,
        model_id: Optional[int] = None,
        scene: AgentScene = AgentScene.UNSCOPED,
    ) -> AsyncIterator[AgentEvent]:
        run = AgentRun(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=ctx.actor.id,
            subject_id=ctx.subject_id,
            surface=ctx.surface.value,
            status=AgentRunStatus.RUNNING,
            model_id=model_id,
        )
        ctx.db.add(run)
        await ctx.db.commit()

        step_idx = 0
        tool_calls_used = 0
        started = time.monotonic()
        full_text = ""
        stop_reason = "completed"

        try:
            for _turn in range(self.budget.max_turns):
                turn_text = ""
                tool_calls: List[ToolCall] = []

                async for chunk in self.provider.chat_stream(
                    messages, self.provider_config, tools=ai_tools.openai_schemas(scene)
                ):
                    if isinstance(chunk, str):
                        full_text += chunk
                        turn_text += chunk
                        yield TextDelta(text=chunk)
                    elif isinstance(chunk, ToolCall):
                        tool_calls.append(chunk)

                if not tool_calls:
                    break

                if tool_calls_used + len(tool_calls) > self.budget.max_tool_calls:
                    stop_reason = "budget_exhausted"
                    break
                if time.monotonic() - started > self.budget.wall_clock_s:
                    stop_reason = "budget_exhausted"
                    break

                messages.append(_assistant_message(turn_text, tool_calls))
                yield AssistantTurn(
                    run_id=run.id,
                    text=turn_text,
                    tool_calls=_serialize_tool_calls(tool_calls),
                )
                ctx.db.add(AgentStep(
                    run_id=run.id, idx=step_idx, type="assistant",
                    result={"text": turn_text, "tool_calls": [tc.name for tc in tool_calls]},
                ))
                step_idx += 1

                for tc in tool_calls:
                    tool_calls_used += 1
                    args = _parse_arguments(tc.arguments)
                    call_args = args if isinstance(args, dict) else {}
                    yield ToolCallStarted(tool_call_id=tc.id, name=tc.name, arguments=args)

                    began = time.monotonic()
                    spec = ai_tools.get(tc.name)
                    if spec is not None and spec.executor == "client" and spec.available_in(scene):
                        # 暂停前必须先提交:SQLAlchemy 在 commit 时把连接还池。
                        # 若带着未结事务等待,十几个并发流就能耗尽连接池并锁死整个 API。
                        await ctx.db.commit()
                        ticket = client_channel.open_ticket(run.id)
                        yield ClientToolRequested(
                            run_id=run.id, tool_call_id=tc.id, name=tc.name,
                            arguments=call_args, ticket=ticket,
                        )
                        result = _client_tool_result(await client_channel.wait_for(ticket))
                    else:
                        result = await ai_tools.dispatch(tc.name, ctx, call_args, scene=scene)
                    latency_ms = int((time.monotonic() - began) * 1000)

                    ctx.db.add(AgentStep(
                        run_id=run.id, idx=step_idx, type="tool_call",
                        tool_name=tc.name, args=args if isinstance(args, dict) else None,
                        result={"content": result.content[:2000], "data": result.data},
                        latency_ms=latency_ms,
                    ))
                    step_idx += 1

                    yield ToolCallFinished(
                        run_id=run.id, tool_call_id=tc.id, name=tc.name,
                        content=result.content, ui=result.ui,
                    )
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result.content,
                    })

                await ctx.db.commit()
            else:
                stop_reason = "budget_exhausted"

            run.status = AgentRunStatus.DONE
            ctx.db.add(run)
            await ctx.db.commit()
            yield RunFinished(run_id=run.id, text=full_text, stop_reason=stop_reason)
        except Exception as exc:  # noqa: BLE001 - run 级失败要落库并告知前端
            logger.exception("Agent run failed")
            run.status = AgentRunStatus.FAILED
            run.error = str(exc)
            ctx.db.add(run)
            await ctx.db.commit()
            yield RunFailed(run_id=run.id, error=str(exc))


def _parse_arguments(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _assistant_message(text: str, tool_calls: List[ToolCall]) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "content": text,
        "tool_calls": _serialize_tool_calls(tool_calls),
    }


def _serialize_tool_calls(tool_calls: List[ToolCall]) -> List[Dict[str, Any]]:
    return [
        {
            "id": tc.id,
            "type": "function",
            "function": {"name": tc.name, "arguments": tc.arguments},
            "metadata": tc.metadata,
        }
        for tc in tool_calls
    ]
