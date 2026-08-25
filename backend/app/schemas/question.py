from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator
from typing import Optional, List, Any, Dict, Literal, Annotated, Union
from datetime import datetime
from app.models.question import QuestionType, QuestionStatus
from app.services.question_content import (
    normalize_options,
    parse_json_field,
    validate_question_domain,
    validate_rich_doc,
)
from .tag import Tag
from .knowledge_point import KnowledgePoint
from .user import User
from .activity_log import ActivityLog
from .subject import Subject
from .import_task import ImportTask


# --------------------------------------------------------------------------- #
# RichDoc:统一富文本原子。ORM 存 JSON 字符串 / API 传对象;before 校验统一解析并校验根节点。
# --------------------------------------------------------------------------- #
def _coerce_rich_doc(v: Any) -> Any:
    return validate_rich_doc(parse_json_field(v))


RichDoc = Annotated[Optional[Dict[str, Any]], BeforeValidator(_coerce_rich_doc)]


# --------------------------------------------------------------------------- #
# Option
# --------------------------------------------------------------------------- #
class Option(BaseModel):
    id: str
    label: str
    content: RichDoc = None

    @field_validator("id")
    @classmethod
    def _id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("option id 不能为空")
        return v


# --------------------------------------------------------------------------- #
# AnswerSpec 判别联合(见 PRD §6)
# --------------------------------------------------------------------------- #
class SingleChoiceAnswer(BaseModel):
    kind: Literal["single_choice"]
    correct: str


class MultipleChoiceAnswer(BaseModel):
    kind: Literal["multiple_choice"]
    correct: List[str]
    grading: Optional[Literal["all_or_nothing", "partial"]] = None


class TrueFalseAnswer(BaseModel):
    kind: Literal["true_false"]
    correct: bool


class Blank(BaseModel):
    id: str
    accept: List[RichDoc]
    match: Optional[Literal["exact", "ignore_space", "ignore_case", "numeric"]] = None

    @field_validator("id")
    @classmethod
    def _id_non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("blank id 不能为空")
        return v

class FillBlankAnswer(BaseModel):
    kind: Literal["fill_in_the_blank"]
    blanks: List[Blank]


class FreeResponseAnswer(BaseModel):
    kind: Literal["free_response"]
    reference: RichDoc = None


class LegacyUnresolvedAnswer(BaseModel):
    kind: Literal["legacy_unresolved"]
    expected_kind: QuestionType
    raw: RichDoc = None


# 读 union(API 响应可读取 legacy_unresolved);写请求另行拒绝 legacy。
AnswerSpec = Annotated[
    Union[
        SingleChoiceAnswer,
        MultipleChoiceAnswer,
        TrueFalseAnswer,
        FillBlankAnswer,
        FreeResponseAnswer,
        LegacyUnresolvedAnswer,
    ],
    Field(discriminator="kind"),
]


def _answer_to_dict(answer: Any) -> Optional[Dict[str, Any]]:
    return answer.model_dump() if answer is not None else None


def _options_to_dicts(options: Any) -> Optional[List[Dict[str, Any]]]:
    return [o.model_dump() for o in options] if options else None


# --------------------------------------------------------------------------- #
# Question schemas
# --------------------------------------------------------------------------- #
class QuestionBase(BaseModel):
    content: RichDoc
    options: Optional[List[Option]] = None
    answer: Optional[AnswerSpec] = None
    thinking: RichDoc = None
    analysis: RichDoc = None
    summary: RichDoc = None
    q_type: QuestionType
    status: QuestionStatus = QuestionStatus.DRAFT
    difficulty: int = 1
    source: Optional[str] = None
    parent_id: Optional[int] = None

    @field_validator("answer", mode="before")
    @classmethod
    def _parse_answer(cls, v: Any) -> Any:
        return parse_json_field(v)


def _reject_legacy(answer: Any) -> None:
    if isinstance(answer, LegacyUnresolvedAnswer):
        raise ValueError("legacy_unresolved 只读,不允许出现在写请求中")


class QuestionCreate(QuestionBase):
    knowledge_point_ids: List[int] = []
    tag_ids: Optional[List[int]] = []
    import_task_id: Optional[int] = None
    subject_id: Optional[int] = None
    ai_suggested_tags: Optional[Dict[str, List[str]]] = None
    children: Optional[List['QuestionCreate']] = None
    temp_id: Optional[str] = None

    # parent_id 允许创建/导入期传入字符串 UUID(占位),CRUD 再落地为真实 id。
    parent_id: Optional[Any] = None

    @model_validator(mode='after')
    def _validate_domain(self) -> 'QuestionCreate':
        _reject_legacy(self.answer)
        self.options = normalize_options(self.q_type, self.options)
        validate_question_domain(
            q_type=self.q_type,
            status=self.status,
            content=self.content,
            options=_options_to_dicts(self.options),
            answer=_answer_to_dict(self.answer),
            partial=False,
        )
        return self


class QuestionBatchCreate(BaseModel):
    filename: Optional[str] = None
    file_path: Optional[str] = None
    questions: List[QuestionCreate]


class QuestionUpdate(QuestionBase):
    content: RichDoc = None
    q_type: Optional[QuestionType] = None
    status: Optional[QuestionStatus] = None
    knowledge_point_ids: Optional[List[int]] = None
    tag_ids: Optional[List[int]] = None
    subject_id: Optional[int] = None

    @model_validator(mode='after')
    def _validate_partial_domain(self) -> 'QuestionUpdate':
        _reject_legacy(self.answer)
        # 不改写 self.options(避免污染 model_fields_set / exclude_unset);
        # 归一化只用于本次 partial 校验,真正落库的归一化由 CRUD 合并现状后执行。
        options = normalize_options(self.q_type, self.options)
        validate_question_domain(
            q_type=self.q_type,
            status=self.status,
            content=self.content,
            options=_options_to_dicts(options),
            answer=_answer_to_dict(self.answer),
            partial=True,
        )
        return self


class QuestionReview(BaseModel):
    status: QuestionStatus
    comment: Optional[str] = None


class QuestionSummary(QuestionBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Question(QuestionBase):
    id: int
    import_task_id: Optional[int] = None
    subject_id: Optional[int] = None
    content_revision: int = 1
    knowledge_points: List[KnowledgePoint] = []
    created_at: datetime
    updated_at: datetime
    tags: List[Tag] = []

    review_count: int = 0
    creator: Optional[User] = None
    updater: Optional[User] = None
    review_logs: List[ActivityLog] = []
    subject: Optional[Subject] = None
    import_task: Optional[ImportTask] = None
    children: Optional[List['Question']] = []
    parent: Optional['QuestionSummary'] = None

    @field_validator('review_count', mode='before')
    @classmethod
    def set_review_count_default(cls, v):
        return v or 0

    class Config:
        from_attributes = True


class QuestionPage(BaseModel):
    items: List[Question]
    total: int
    page: int
    size: int
    pages: int


class QuestionBatchConfirm(BaseModel):
    question_ids: List[int]
    action: str # "approve" or "reject"


class QuestionBatchDelete(BaseModel):
    ids: List[int]


class QuestionBatchUpdate(BaseModel):
    ids: List[int]
    source: Optional[str] = None


Question.model_rebuild()


# --------------------------------------------------------------------------- #
# Legacy 导入(智能导入工作台):旧字符串形态 payload,由后端 adapter 转 v2。
# 严格 QuestionCreate 不接受旧格式;前端不复制 Python 解析规则。
# --------------------------------------------------------------------------- #
class LegacyQuestionCreate(BaseModel):
    content: Optional[str] = None
    q_type: QuestionType
    options: Optional[List[Any]] = None
    answer: Optional[Any] = None
    thinking: Optional[str] = None
    analysis: Optional[str] = None
    summary: Optional[str] = None
    difficulty: int = 1
    knowledge_point_ids: List[int] = []
    tag_ids: Optional[List[int]] = []
    subject_id: Optional[int] = None
    ai_suggested_tags: Optional[Dict[str, List[str]]] = None
    status: QuestionStatus = QuestionStatus.PENDING
    source: Optional[str] = None


class LegacyQuestionBatchCreate(BaseModel):
    filename: Optional[str] = None
    file_path: Optional[str] = None
    questions: List[LegacyQuestionCreate]


class LegacyBatchError(BaseModel):
    index: int
    message: str


class LegacyBatchResult(BaseModel):
    import_task_id: Optional[int] = None
    created: List[Question] = []
    failed: List[LegacyBatchError] = []
