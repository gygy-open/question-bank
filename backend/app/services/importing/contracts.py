"""导入管线共享契约(DTO / TypedDict)。

RawQuestion 刻意保持"legacy 字符串形态"的 dict——它就是 `adapt_legacy_question`
归一化漏斗的输入契约;各抽取策略(AI / 结构化模板)都产出这个形态,不各自造 v2。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, TypedDict

from app.models.question import QuestionStatus


class RawQuestion(TypedDict, total=False):
    """抽取阶段产物:旧字符串形态,喂给归一化漏斗。字段全部可选。"""

    q_type: Any                       # str | QuestionType
    type: Any                         # 旧别名,兼容
    content: Optional[str]            # Markdown
    options: Optional[list]           # List[str] 或 List[{label, content}]
    answer: Any                       # str | List[List[str]] | ...
    thinking: Optional[str]
    analysis: Optional[str]
    summary: Optional[str]
    difficulty: Optional[int]
    knowledge_point_ids: Optional[list]
    tag_ids: Optional[list]
    subject_id: Optional[int]
    ai_suggested_tags: Optional[dict]
    tags: Optional[list]              # AI 抽取的建议标签,归一化时并入 ai_suggested_tags
    status: Any                       # 逐题状态覆盖(缺省用 ImportDefaults.status)
    source: Optional[str]


@dataclass
class ImportDefaults:
    """批次级兜底元数据;逐题字段缺失时回退到这里。"""

    subject_id: Optional[int] = None
    status: QuestionStatus = QuestionStatus.PENDING
    source: Optional[str] = None


@dataclass
class FailedItem:
    index: int
    message: str


@dataclass
class NormalizeReport:
    """归一化 + 落库的结果汇总;worker 取计数,batch-legacy 取明细。"""

    created: List[Any] = field(default_factory=list)   # list[models.Question]
    failed: List[FailedItem] = field(default_factory=list)

    @property
    def saved_count(self) -> int:
        return len(self.created)

    @property
    def failed_count(self) -> int:
        return len(self.failed)
