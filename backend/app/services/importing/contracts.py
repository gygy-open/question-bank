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


# --------------------------------------------------------------------------- #
# 整卷结构(Paper)契约
#
# 解析器只描述"识别事实",不产出组稿 AST —— 节点 id / node_kind / slot / 题目冻结快照
# 都是系统拥有的字段。翻译成 AST 由 composition_authoring.build_nodes 负责。
# outline 里的 question_ref.temp_id 指向 questions[].id(同一次抽取内唯一)。
# --------------------------------------------------------------------------- #

OUTLINE_HEADING = "heading"
OUTLINE_RICH_TEXT = "rich_text"
OUTLINE_QUESTION_REF = "question_ref"
OUTLINE_PAGE_BREAK = "page_break"
OUTLINE_ANSWER_SPACE = "answer_space"
OUTLINE_DETAILS_MODULE = "details_module"
# 超出稿件模型表达力的结构:降级保留内容,不丢题、不阻塞整卷生成。
OUTLINE_DEGRADED = "degraded"

OUTLINE_KINDS = frozenset(
    {
        OUTLINE_HEADING,
        OUTLINE_RICH_TEXT,
        OUTLINE_QUESTION_REF,
        OUTLINE_PAGE_BREAK,
        OUTLINE_ANSWER_SPACE,
        OUTLINE_DETAILS_MODULE,
        OUTLINE_DEGRADED,
    }
)


class PaperOutlineItem(TypedDict, total=False):
    """整卷版面中的一项。字段按 kind 取用,全部可选。"""

    kind: str
    # heading
    text: str
    level: int
    # rich_text / degraded
    markdown: str
    reason: str
    # question_ref
    temp_id: str
    number: Optional[str]
    score: Optional[float]
    # answer_space
    lines: int
    style: str
    # details_module
    scope: str
    fields: dict


class PaperExtraction(TypedDict, total=False):
    """一份试卷的整卷结构;与 questions 并列返回,二者靠 temp_id 关联。"""

    suggested_title: Optional[str]
    outline: List[PaperOutlineItem]


@dataclass
class ExtractionResult:
    """抽取阶段的完整产物。paper 为 None 表示该路径未识别整卷结构。"""

    questions: List[dict] = field(default_factory=list)
    paper: Optional[PaperExtraction] = None


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
