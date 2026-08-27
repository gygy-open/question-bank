"""组稿导出中间契约:把 CompositionVersion.snapshot 装配成渲染器无关的节点树。

与 Paper 的 `contracts.py` 相互独立(避免 `ExportQuestion` 等类名冲突);选项结构与
Paper 完全一致,直接复用其 `ExportOption`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from app.services.exporting.contracts import ExportOption

# RichDoc:一个 Tiptap doc(dict)或空。
RichDoc = Optional[dict[str, Any]]


@dataclass
class ExportRichTextNode:
    content: RichDoc


@dataclass
class ExportHeadingNode:
    level: int
    content: RichDoc


@dataclass
class ExportQuestionNode:
    number: str                       # ''  = 不显示(numbering_enabled 为假或未赋值)
    score: Optional[float]            # None = 不显示(scoring_enabled 为假或未赋值)
    q_type: str
    stem: RichDoc
    options: list[ExportOption]
    option_columns: int
    answer: Optional[dict[str, Any]]  # None = 不内联显示(effective show 解析后)
    thinking: RichDoc
    analysis: RichDoc
    summary: RichDoc


@dataclass
class ExportPageBreakNode:
    pass


@dataclass
class ExportAnswerEntry:
    """question_details 模块内一条已解析的 answer_item:源题冻结内容 + 有效字段。"""
    question_id: int
    q_type: str
    stem: RichDoc
    options: list[ExportOption]
    answer: Optional[dict[str, Any]]
    thinking: RichDoc
    analysis: RichDoc
    summary: RichDoc


# question_details 的子节点:自定义 heading/rich_text 原样透传,或已解析的 answer_item。
QuestionDetailsChild = Union[ExportHeadingNode, ExportRichTextNode, ExportAnswerEntry]


@dataclass
class ExportQuestionDetailsNode:
    scope: str  # "before" | "all"
    children: list[QuestionDetailsChild] = field(default_factory=list)


CompositionExportNode = Union[
    ExportRichTextNode,
    ExportHeadingNode,
    ExportQuestionNode,
    ExportPageBreakNode,
    ExportQuestionDetailsNode,
]


@dataclass
class CompositionExportDoc:
    title: str
    nodes: list[CompositionExportNode] = field(default_factory=list)
