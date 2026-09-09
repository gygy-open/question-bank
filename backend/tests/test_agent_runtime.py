"""AgentRunner 的行为契约。

用脚本化的 FakeProvider 驱动工具循环 —— 这段逻辑此前焊死在 SSE generator 里,
根本没法单测,预算控制、错误处理、上下文拼接都只能靠线上跑。
"""
from typing import Any, AsyncGenerator, Dict, List, Union

import pytest
from sqlalchemy import select

from app.ai.events import AssistantTurn, RunFinished, TextDelta, ToolCallFinished, ToolCallStarted
from app.ai.runtime import AgentRunner, RunBudget
from app.capabilities.context import ExecutionContext, Surface
from app.crud.crud_user import user as crud_user
from app.models.agent import AgentRun, AgentRunStatus, AgentStep
from app.models.question import Question
from app.models.subject import Subject
from app.models.subject_member import SubjectMember
from app.models.user import User
from app.services.ai_provider import AIProvider, ToolCall


class FakeProvider(AIProvider):
    """按剧本逐轮吐 chunk。每个 turn 是一个 list,元素为 str 或 ToolCall。"""

    def __init__(self, script: List[List[Union[str, ToolCall]]]):
        self.script = script
        self.calls: List[List[Dict[str, Any]]] = []

    async def chat_stream(self, messages, config, tools=None) -> AsyncGenerator[Any, None]:
        # 记录每轮看到的完整上下文,断言历史拼接是否正确。
        self.calls.append([dict(m) for m in messages])
        turn = self.script[len(self.calls) - 1] if len(self.calls) <= len(self.script) else []
        for chunk in turn:
            yield chunk

    async def extract_questions(self, content, image_data=None, config=None):
        raise NotImplementedError

    async def get_embeddings(self, texts, config=None):
        raise NotImplementedError

    async def rerank_knowledge_points(self, question_content, candidates, config=None):
        raise NotImplementedError

    async def batch_rerank_knowledge_points(self, items, config=None):
        raise NotImplementedError


def _tool_call(call_id: str, name: str, arguments: str = "{}") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


_DRAFT_ARGS = '{"content": "1+1=?", "q_type": "free_response", "answer": "2"}'


@pytest.fixture
async def ctx(db_session):
    subject = Subject(name="数学", slug="math")
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)

    editor = User(username="e", full_name="e", hashed_password="x", is_active=True)
    db_session.add(editor)
    await db_session.commit()
    await db_session.refresh(editor)
    db_session.add(SubjectMember(user_id=editor.id, subject_id=subject.id, role="editor"))
    await db_session.commit()

    actor = await crud_user.get_with_memberships(db_session, id=editor.id)
    return ExecutionContext(
        db=db_session, actor=actor, surface=Surface.CHAT, subject_id=subject.id
    )


async def _drain(runner, ctx, messages):
    return [event async for event in runner.run(ctx, messages)]


async def test_plain_answer_emits_text_and_finishes(ctx):
    runner = AgentRunner(FakeProvider([["你好", "世界"]]), {})
    events = await _drain(runner, ctx, [{"role": "user", "content": "hi"}])

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["你好", "世界"]
    finished = events[-1]
    assert isinstance(finished, RunFinished)
    assert finished.text == "你好世界"
    assert finished.stop_reason == "completed"


async def test_tool_round_trip_feeds_result_back_to_the_model(ctx):
    provider = FakeProvider([
        [_tool_call("c1", "get_available_tags")],
        ["好的"],
    ])
    runner = AgentRunner(provider, {})
    events = await _drain(runner, ctx, [{"role": "user", "content": "有哪些标签"}])

    assert any(isinstance(e, ToolCallStarted) for e in events)
    assert any(isinstance(e, ToolCallFinished) for e in events)

    # 第二轮的上下文里,assistant(tool_calls) 与 tool 结果必须成对出现。
    second_turn = provider.calls[1]
    assert second_turn[-2]["role"] == "assistant"
    assert second_turn[-2]["tool_calls"][0]["function"]["name"] == "get_available_tags"
    assert second_turn[-1]["role"] == "tool"
    assert second_turn[-1]["tool_call_id"] == "c1"


async def test_assistant_turn_event_carries_tool_calls_for_persistence(ctx):
    provider = FakeProvider([[_tool_call("c1", "get_available_tags")], ["ok"]])
    events = await _drain(AgentRunner(provider, {}), ctx, [{"role": "user", "content": "x"}])

    turns = [e for e in events if isinstance(e, AssistantTurn)]
    assert len(turns) == 1
    assert turns[0].tool_calls[0]["id"] == "c1"


async def test_tool_permission_denial_does_not_abort_the_run(db_session, ctx):
    """viewer 调写工具被拒 —— 错误回喂模型,循环继续,不炸整轮对话。"""
    viewer = User(username="v", full_name="v", hashed_password="x", is_active=True)
    db_session.add(viewer)
    await db_session.commit()
    await db_session.refresh(viewer)
    db_session.add(SubjectMember(user_id=viewer.id, subject_id=ctx.subject_id, role="viewer"))
    await db_session.commit()
    viewer_ctx = ExecutionContext(
        db=db_session,
        actor=await crud_user.get_with_memberships(db_session, id=viewer.id),
        surface=Surface.CHAT,
        subject_id=ctx.subject_id,
    )

    provider = FakeProvider([
        [_tool_call("c1", "propose_question_draft", _DRAFT_ARGS)],
        ["抱歉，你没有权限"],
    ])
    events = await _drain(AgentRunner(provider, {}), viewer_ctx, [{"role": "user", "content": "建题"}])

    result = next(e for e in events if isinstance(e, ToolCallFinished))
    assert "privileges" in result.content
    assert isinstance(events[-1], RunFinished)
    assert not (await db_session.execute(select(Question))).scalars().all()


async def test_failing_tool_is_reported_to_the_model_not_raised(ctx):
    provider = FakeProvider([[_tool_call("c1", "nope_not_a_tool")], ["ok"]])
    events = await _drain(AgentRunner(provider, {}), ctx, [{"role": "user", "content": "x"}])

    result = next(e for e in events if isinstance(e, ToolCallFinished))
    assert "not found" in result.content
    assert isinstance(events[-1], RunFinished)


async def test_turn_budget_stops_the_loop(ctx):
    # 模型每轮都要调工具,永不收敛。
    provider = FakeProvider([[_tool_call(f"c{i}", "get_available_tags")] for i in range(10)])
    runner = AgentRunner(provider, {}, RunBudget(max_turns=3))
    events = await _drain(runner, ctx, [{"role": "user", "content": "x"}])

    assert len(provider.calls) == 3
    assert events[-1].stop_reason == "budget_exhausted"


async def test_tool_call_budget_stops_the_loop(ctx):
    provider = FakeProvider([[_tool_call(f"c{i}", "get_available_tags")] for i in range(10)])
    runner = AgentRunner(provider, {}, RunBudget(max_turns=10, max_tool_calls=2))
    events = await _drain(runner, ctx, [{"role": "user", "content": "x"}])

    assert len([e for e in events if isinstance(e, ToolCallStarted)]) == 2
    assert events[-1].stop_reason == "budget_exhausted"


async def test_run_and_steps_are_persisted(db_session, ctx):
    provider = FakeProvider([[_tool_call("c1", "get_available_tags")], ["done"]])
    await _drain(AgentRunner(provider, {}), ctx, [{"role": "user", "content": "x"}])

    run = (await db_session.execute(select(AgentRun))).scalars().one()
    assert run.status == AgentRunStatus.DONE
    assert run.surface == Surface.CHAT.value
    assert run.user_id == ctx.actor.id

    steps = (await db_session.execute(select(AgentStep).order_by(AgentStep.idx))).scalars().all()
    assert [s.type for s in steps] == ["assistant", "tool_call"]
    assert steps[1].tool_name == "get_available_tags"
    assert steps[1].latency_ms is not None
