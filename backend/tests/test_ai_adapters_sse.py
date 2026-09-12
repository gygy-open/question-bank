"""SSE 适配器契约:工具相关帧必须携带 tool_call_id,前端才能把 action /
action_result / client_tool 精确关联到同一次工具调用。"""
import json

from app.ai.adapters.sse import to_sse
from app.ai.contracts import UIDirective
from app.ai.events import (
    ClientToolRequested,
    ToolCallFinished,
    ToolCallStarted,
)


def _frames(event):
    """把 to_sse 产出的 SSE 文本拆成 (event_name, data_dict) 列表。"""
    out = []
    for frame in to_sse(event):
        head, _, body = frame.partition("\n")
        assert head.startswith("event: ")
        name = head[len("event: "):]
        data_line = body.splitlines()[0]
        assert data_line.startswith("data: ")
        out.append((name, json.loads(data_line[len("data: "):])))
    return out


def test_action_frame_carries_tool_call_id():
    frames = _frames(ToolCallStarted(tool_call_id="call-1", name="search", arguments={"q": "x"}))
    assert frames == [("action", {"tool_call_id": "call-1", "tool": "search", "input": {"q": "x"}})]


def test_client_tool_frame_carries_tool_call_id():
    event = ClientToolRequested(
        run_id="run-1",
        tool_call_id="call-2",
        name="pick_file",
        arguments={"types": ["png"]},
        ticket="tkt-1",
    )
    (name, payload), = _frames(event)
    assert name == "client_tool"
    assert payload["tool_call_id"] == "call-2"
    assert payload["run_id"] == "run-1"
    assert payload["ticket"] == "tkt-1"
    assert payload["tool"] == "pick_file"
    assert payload["input"] == {"types": ["png"]}


def test_action_result_frame_carries_tool_call_id():
    event = ToolCallFinished(
        run_id="run-1",
        tool_call_id="call-3",
        name="search",
        content="done",
    )
    (name, payload), = _frames(event)
    assert name == "action_result"
    assert payload == {"tool_call_id": "call-3", "tool": "search", "output": "done"}


def test_action_result_emits_ui_directives_before_result():
    event = ToolCallFinished(
        run_id="run-1",
        tool_call_id="call-4",
        name="propose",
        content="ok",
        ui=[UIDirective(kind="proposal", payload={"type": "single", "ids": [1]})],
    )
    frames = _frames(event)
    assert frames[0][0] == "proposal"
    assert frames[-1] == ("action_result", {"tool_call_id": "call-4", "tool": "propose", "output": "ok"})
