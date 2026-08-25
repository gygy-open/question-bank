"""导出中间文档契约:装配阶段把 Paper 拍平成渲染器无关的结构树。

选项/答案保持结构化(不提前拍成散文),渲染器再决定各自的 native 映射
(LaTeX 的 \\begin{choices}、DOCX 的编号段落等)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# RichDoc:一个 Tiptap doc(dict)或空。
RichDoc = Optional[dict[str, Any]]


@dataclass
class ExportOption:
    id: str
    label: str
    content: RichDoc


@dataclass
class ExportQuestion:
    number: int
    q_type: str
    stem: RichDoc
    options: list[ExportOption]
    answer: Optional[dict[str, Any]]      # 解析后的 AnswerSpec dict
    thinking: RichDoc
    analysis: RichDoc
    summary: RichDoc
    source: Optional[str]
    reserve_space: bool                   # free_response 预留答题区


@dataclass
class ExportSection:
    title: Optional[str]
    questions: list[ExportQuestion] = field(default_factory=list)


@dataclass
class ExportDoc:
    title: str
    sections: list[ExportSection]         # 题目主体
    appendix: list[ExportSection]         # END_OF_PAPER 时的答案册
    has_appendix: bool


@dataclass
class ExportOptions:
    title: str
    include_answer: bool = True
    include_analysis: bool = True         # thinking
    include_explanation: bool = True      # analysis
    include_summary: bool = True
    include_source: bool = False
    details_at_end: bool = False          # END_OF_PAPER
    hidden_details: bool = False          # HIDDEN:全部细节不出


@dataclass
class RenderedFile:
    path: str
    ext: str
