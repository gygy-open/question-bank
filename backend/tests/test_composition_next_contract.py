"""单一 tiptap 文档模型（composition-next）与现有节点契约的兼容性回归测试。

结论锁定：新画布把每个顶层块存为一行 —— rich_text 行携带「恰好一个」块级节点
（paragraph / list / table / blockquote / codeBlock / horizontalRule / blockMath / image），
heading 行仍是「单段落 + 行内内容」。这些形态无需扩展 node_type / 迁移即被现有
CompositionNodeInput 契约接受。此测试防止后续对校验器的收紧误伤新模型。
"""
import uuid

import pytest
from pydantic import ValidationError

from app.schemas.composition import CompositionNodeInput


def _uid() -> str:
    return str(uuid.uuid4())


def _doc(*blocks: dict) -> dict:
    return {"type": "doc", "content": list(blocks)}


def _rich_text(block: dict) -> CompositionNodeInput:
    return CompositionNodeInput(
        id=_uid(), node_kind="block", node_type="rich_text", content=_doc(block)
    )


# 单块 rich_text 覆盖新画布可产出的各类顶层块。
_SINGLE_BLOCKS = {
    "paragraph": {"type": "paragraph", "content": [{"type": "text", "text": "hi"}]},
    "bulletList": {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "a"}]}]}
        ],
    },
    "orderedList": {
        "type": "orderedList",
        "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "1"}]}]}
        ],
    },
    "blockquote": {
        "type": "blockquote",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "q"}]}],
    },
    "codeBlock": {"type": "codeBlock", "content": [{"type": "text", "text": "print(1)"}]},
    "horizontalRule": {"type": "horizontalRule"},
    "blockMath": {"type": "blockMath", "attrs": {"latex": "x^2"}},
    "table": {
        "type": "table",
        "content": [
            {
                "type": "tableRow",
                "content": [
                    {"type": "tableCell", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "c"}]}]}
                ],
            }
        ],
    },
    "image": {"type": "image", "attrs": {"src": "data:image/png;base64,AAAA", "width": 100, "height": 80}},
}


@pytest.mark.parametrize("name,block", list(_SINGLE_BLOCKS.items()))
def test_single_block_rich_text_is_accepted(name: str, block: dict) -> None:
    node = _rich_text(block)
    assert node.node_type == "rich_text"
    assert node.content is not None
    assert len(node.content["content"]) == 1


def test_heading_with_inline_math_and_marks_is_accepted() -> None:
    node = CompositionNodeInput(
        id=_uid(),
        node_kind="block",
        node_type="heading",
        content=_doc(
            {
                "type": "paragraph",
                "attrs": {"textAlign": "center"},
                "content": [
                    {"type": "text", "text": "E=", "marks": [{"type": "bold"}]},
                    {"type": "inlineMath", "attrs": {"latex": "mc^2"}},
                ],
            }
        ),
        props={"level": 2},
    )
    assert node.props == {"level": 2}


def test_page_break_node_is_accepted() -> None:
    node = CompositionNodeInput(id=_uid(), node_kind="block", node_type="page_break")
    assert node.node_type == "page_break"


def test_answer_space_node_is_accepted() -> None:
    node = CompositionNodeInput(
        id=_uid(), node_kind="block", node_type="answer_space",
        props={"lines": 5, "style": "lined"},
    )
    assert node.node_type == "answer_space"
    assert node.props == {"lines": 5, "style": "lined"}


def test_answer_space_rejects_bad_props() -> None:
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), node_kind="block", node_type="answer_space",
            props={"lines": 0, "style": "blank"},
        )
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), node_kind="block", node_type="answer_space",
            props={"lines": 3, "style": "dotted"},
        )
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), node_kind="block", node_type="answer_space",
            content=_doc({"type": "paragraph"}), props={"lines": 3, "style": "blank"},
        )


def test_answer_space_must_be_root_level() -> None:
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(), parent_id=_uid(), slot="body", node_kind="block",
            node_type="answer_space", props={"lines": 3, "style": "blank"},
        )



def test_heading_rejects_nested_block_content() -> None:
    # 防御：heading 段落内若混入块级节点应被拒（convert 永不产出此形态）。
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(),
            node_kind="block",
            node_type="heading",
            content=_doc(
                {"type": "paragraph", "content": [{"type": "bulletList", "content": []}]}
            ),
            props={"level": 1},
        )


_TWO_BLOCKS = (
    {"type": "paragraph", "content": [{"type": "text", "text": "a"}]},
    {"type": "paragraph", "content": [{"type": "text", "text": "b"}]},
)


def test_v2_rich_text_accepts_single_block() -> None:
    node = CompositionNodeInput(
        id=_uid(),
        node_kind="block",
        node_type="rich_text",
        content=_doc(_SINGLE_BLOCKS["paragraph"]),
        schema_version=2,
    )
    assert node.schema_version == 2


def test_v2_rich_text_rejects_multi_block() -> None:
    with pytest.raises(ValidationError):
        CompositionNodeInput(
            id=_uid(),
            node_kind="block",
            node_type="rich_text",
            content=_doc(*_TWO_BLOCKS),
            schema_version=2,
        )


def test_v1_rich_text_still_tolerates_multi_block() -> None:
    # 向后兼容：旧画布产出的多块 rich_text（schema_version 默认 1）仍合法。
    node = CompositionNodeInput(
        id=_uid(),
        node_kind="block",
        node_type="rich_text",
        content=_doc(*_TWO_BLOCKS),
    )
    assert node.schema_version == 1
    assert len(node.content["content"]) == 2
