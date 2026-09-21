"""把 AI 的「意图节点」翻译成组稿 AST 的 `CompositionNodeInput`。

模型不直接产出 AST:节点 id、node_kind、slot、question 的冻结快照都是系统拥有的字段,
让模型自己编要么出错、要么和题库对不上。模型只提供意图与引用,这里负责构造。

正文走 Markdown 而不是 tiptap JSON:公式要嵌 inlineMath/blockMath、表格是三层嵌套,
模型直接产出 JSON 的结构错误率很高,token 也是 Markdown 的数倍。转换复用后端已有的
`question_content_converter`,不在前端再实现一份(两份实现必然漂移)。
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from app.models.composition import (
    BODY_SLOT,
    BLOCK_NODE_TYPES,
    MODULE_NODE_TYPES,
    NODE_TYPE_ANSWER_SPACE,
    NODE_TYPE_HEADING,
    NODE_TYPE_PAGE_BREAK,
    NODE_TYPE_QUESTION,
    NODE_TYPE_QUESTION_DETAILS,
    NODE_TYPE_QUESTION_GROUP,
    NODE_TYPE_RICH_TEXT,
    REFERENCE_NODE_TYPES,
    CompositionNodeKind,
)
from app.schemas.composition import ANSWER_FIELD_KEYS, CompositionNodeInput
from app.services.answer_space import resolve_answer_space_props_or_fallback
from app.services.question_content_converter import markdown_to_rich_doc

# AI 可以直接书写的节点类型。answer_item 不在其中 —— 它由服务端按 module scope 派生。
AUTHORABLE_NODE_TYPES = (
    NODE_TYPE_HEADING,
    NODE_TYPE_RICH_TEXT,
    NODE_TYPE_QUESTION,
    NODE_TYPE_QUESTION_DETAILS,
    NODE_TYPE_QUESTION_GROUP,
    NODE_TYPE_PAGE_BREAK,
    NODE_TYPE_ANSWER_SPACE,
)

# 画布每行恰好一个顶层块;拆出来的 rich_text 都按 v2 标记,与画布产出同源。
_RICH_TEXT_SCHEMA_VERSION = 2


class AuthoringError(ValueError):
    """AI 给的节点描述不合法。文案要能直接回喂给模型让它自己改。"""


def _new_id() -> str:
    return str(uuid.uuid4())


def _kind_for(node_type: str) -> CompositionNodeKind:
    if node_type in BLOCK_NODE_TYPES:
        return CompositionNodeKind.BLOCK
    if node_type in MODULE_NODE_TYPES:
        return CompositionNodeKind.MODULE
    if node_type in REFERENCE_NODE_TYPES:
        return CompositionNodeKind.REFERENCE
    raise AuthoringError(f"unknown node type: {node_type}")


def _heading_doc(text: str) -> Dict[str, Any]:
    """标题必须是「恰好一个 paragraph + 纯内联」,所以不能走 Markdown 转换。"""
    content = [{"type": "text", "text": text}] if text else []
    return {"type": "doc", "content": [{"type": "paragraph", "content": content}]}


def _int_or_none(value: Any, *, field: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise AuthoringError(f"{field} must be an integer")
    return value


def _question_props(spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    props: Dict[str, Any] = {}
    if spec.get("number") is not None:
        props["number"] = str(spec["number"])[:16]
    score = spec.get("score")
    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise AuthoringError("question.score must be a number")
        props["score"] = score
    show = spec.get("show")
    if show is not None:
        if not isinstance(show, dict):
            raise AuthoringError("question.show must be an object")
        unknown = set(show) - set(ANSWER_FIELD_KEYS)
        if unknown:
            raise AuthoringError(
                f"question.show keys must be within {list(ANSWER_FIELD_KEYS)}, got {sorted(unknown)}"
            )
        props["show"] = {k: bool(v) for k, v in show.items()}
    return props or None


def _details_props(spec: Dict[str, Any]) -> Dict[str, Any]:
    scope = spec.get("details_scope") or "all"
    if scope not in ("all", "before"):
        raise AuthoringError("question_details.details_scope must be 'all' or 'before'")
    given = spec.get("details_fields") or {"answer": True}
    if not isinstance(given, dict):
        raise AuthoringError("question_details.details_fields must be an object")
    unknown = set(given) - set(ANSWER_FIELD_KEYS)
    if unknown:
        raise AuthoringError(
            f"question_details.details_fields keys must be within {list(ANSWER_FIELD_KEYS)}, "
            f"got {sorted(unknown)}"
        )
    # 契约要求四个 key 齐全,缺的补 False。
    return {"scope": scope, "fields": {k: bool(given.get(k, False)) for k in ANSWER_FIELD_KEYS}}


def markdown_to_rich_doc_blocks(markdown: str) -> List[Dict[str, Any]]:
    """一段 Markdown → N 个「恰好一个顶层块」的 RichDoc。

    画布加载多块节点时本就会把它拆成 N 行并重新发号,所以这里直接按它的最终形态产出,
    避免稿件一打开 node id 就变。空内容返回空列表(空 rich_text 不合法)。
    """
    doc = markdown_to_rich_doc(markdown)
    blocks = (doc or {}).get("content") or []
    return [{"type": "doc", "content": [block]} for block in blocks]


def _rich_text_nodes(markdown: str) -> List[CompositionNodeInput]:
    return [
        CompositionNodeInput(
            id=_new_id(),
            node_kind=CompositionNodeKind.BLOCK,
            node_type=NODE_TYPE_RICH_TEXT,
            content=doc,
            schema_version=_RICH_TEXT_SCHEMA_VERSION,
        )
        for doc in markdown_to_rich_doc_blocks(markdown)
    ]


def _rich_doc_nodes(content: Any) -> List[CompositionNodeInput]:
    if not isinstance(content, dict) or content.get("type") != "doc":
        raise AuthoringError("rich_text.content must be a RichDoc")
    blocks = content.get("content")
    if not isinstance(blocks, list) or not blocks:
        raise AuthoringError("rich_text.content requires at least one block")
    return [
        CompositionNodeInput(
            id=_new_id(),
            node_kind=CompositionNodeKind.BLOCK,
            node_type=NODE_TYPE_RICH_TEXT,
            content={"type": "doc", "content": [block]},
            schema_version=_RICH_TEXT_SCHEMA_VERSION,
        )
        for block in blocks
    ]


def build_nodes(specs: List[Dict[str, Any]]) -> List[CompositionNodeInput]:
    """把 AI 给的扁平节点列表翻译成 AST。顺序即版面顺序。"""
    if not isinstance(specs, list):
        raise AuthoringError("nodes must be a list")

    nodes: List[CompositionNodeInput] = []
    for idx, spec in enumerate(specs):
        if not isinstance(spec, dict):
            raise AuthoringError(f"nodes[{idx}] must be an object")
        node_type = spec.get("type")
        if node_type not in AUTHORABLE_NODE_TYPES:
            raise AuthoringError(
                f"nodes[{idx}].type must be one of {list(AUTHORABLE_NODE_TYPES)}, got {node_type!r}"
            )

        if node_type == NODE_TYPE_RICH_TEXT:
            produced = (
                _rich_doc_nodes(spec["content"])
                if spec.get("content") is not None
                else _rich_text_nodes(spec.get("markdown") or "")
            )
            if not produced:
                raise AuthoringError(f"nodes[{idx}] rich_text requires non-empty markdown")
            nodes.extend(produced)
            continue

        if node_type == NODE_TYPE_HEADING:
            text = (spec.get("text") or "").strip()
            if not text:
                raise AuthoringError(f"nodes[{idx}] heading requires text")
            level = _int_or_none(spec.get("level"), field=f"nodes[{idx}].level") or 2
            if not 1 <= level <= 4:
                raise AuthoringError(f"nodes[{idx}].level must be in 1..4")
            nodes.append(CompositionNodeInput(
                id=_new_id(),
                node_kind=CompositionNodeKind.BLOCK,
                node_type=NODE_TYPE_HEADING,
                content=_heading_doc(text),
                props={"level": level},
            ))
            continue

        if node_type == NODE_TYPE_QUESTION:
            question_id = _int_or_none(spec.get("question_id"), field=f"nodes[{idx}].question_id")
            if question_id is None:
                raise AuthoringError(f"nodes[{idx}] question requires question_id")
            nodes.append(CompositionNodeInput(
                id=_new_id(),
                node_kind=CompositionNodeKind.BLOCK,
                node_type=NODE_TYPE_QUESTION,
                question_id=question_id,
                props=_question_props(spec),
            ))
            continue

        if node_type == NODE_TYPE_QUESTION_DETAILS:
            # 只发模块本身,answer_item 子节点由 replace_nodes 按 scope 自动派生。
            nodes.append(CompositionNodeInput(
                id=_new_id(),
                node_kind=CompositionNodeKind.MODULE,
                node_type=NODE_TYPE_QUESTION_DETAILS,
                props=_details_props(spec),
            ))
            continue

        if node_type == NODE_TYPE_QUESTION_GROUP:
            question_group_id = _int_or_none(
                spec.get("question_group_id"),
                field=f"nodes[{idx}].question_group_id",
            )
            if question_group_id is None:
                raise AuthoringError(
                    f"nodes[{idx}] question_group requires question_group_id"
                )
            nodes.append(CompositionNodeInput(
                id=_new_id(),
                node_kind=CompositionNodeKind.MODULE,
                node_type=NODE_TYPE_QUESTION_GROUP,
                question_group_id=question_group_id,
            ))
            continue

        if node_type == NODE_TYPE_PAGE_BREAK:
            nodes.append(CompositionNodeInput(
                id=_new_id(),
                node_kind=CompositionNodeKind.BLOCK,
                node_type=NODE_TYPE_PAGE_BREAK,
            ))
            continue

        if node_type == NODE_TYPE_ANSWER_SPACE:
            lines = _int_or_none(spec.get("lines"), field=f"nodes[{idx}].lines")
            defaults = resolve_answer_space_props_or_fallback(
                q_type=spec.get("q_type"), score=spec.get("score")
            )
            nodes.append(CompositionNodeInput(
                id=_new_id(),
                node_kind=CompositionNodeKind.BLOCK,
                node_type=NODE_TYPE_ANSWER_SPACE,
                props={
                    "lines": lines or defaults["lines"],
                    "style": spec.get("style") or defaults["style"],
                },
            ))
            continue

    return nodes
