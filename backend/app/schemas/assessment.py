"""通用评测 (Assessment) 域 Pydantic schemas。

覆盖:名册、评测身份/版本、投放 session、追加式评分、gradebook 与 item 统计。
服务层多数返回 dict 投影(避免异步惰性加载),故这些 schema 直接对 dict 校验。
"""
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# 学生 / 班级名册
# --------------------------------------------------------------------------- #
class StudentCreateRequest(BaseModel):
    student_no: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    user_id: Optional[int] = None


class StudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    user_id: Optional[int] = None
    student_no: str
    name: str


class StudentPage(BaseModel):
    items: List[StudentRead]
    total: int
    page: int
    page_size: int


class ClassroomCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class ClassroomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    name: str


class ClassroomMembersReplaceRequest(BaseModel):
    student_ids: List[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 评测身份 / 版本
# --------------------------------------------------------------------------- #
class AssessmentCreateRequest(BaseModel):
    """从一个 shared 组稿定稿版本 + 班级创建评测(身份 + v1 + 投放)。"""
    title: str = Field(min_length=1, max_length=255)
    composition_version_id: int
    classroom_id: int
    session_name: Optional[str] = Field(default=None, max_length=255)


class AssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    title: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


class AssessmentVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    assessment_id: int
    version_no: int
    composition_version_id: Optional[int] = None
    source_type: str
    total_score: Optional[Decimal] = None
    item_count: Optional[int] = None
    created_at: datetime


class AssessmentItemRead(BaseModel):
    """公开条目投影:不含私有 scoring_spec。"""
    id: int
    item_key: str
    position: int
    item_type: str
    max_score: Decimal
    parent_item_id: Optional[int] = None
    source_question_id: Optional[int] = None
    source_question_revision: Optional[int] = None


class AssessmentDetail(AssessmentRead):
    versions: List[AssessmentVersionRead] = Field(default_factory=list)
    current_items: List[AssessmentItemRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 投放 session
# --------------------------------------------------------------------------- #
class AttemptSummary(BaseModel):
    attempt_id: int
    attempt_no: int
    mode: str
    status: str
    revision: int
    total_score: Optional[Decimal] = None
    max_score: Optional[Decimal] = None
    answered_count: int
    graded_count: int


class ParticipationRead(BaseModel):
    id: int
    participant_key: str
    student_id: Optional[int] = None
    user_id: Optional[int] = None
    display_name: Optional[str] = None
    identifier: Optional[str] = None
    attendance_status: str
    status: str
    attempts: List[AttemptSummary] = Field(default_factory=list)


class SessionRead(BaseModel):
    id: int
    assessment_id: int
    assessment_title: Optional[str] = None
    version_id: int
    subject_id: int
    name: str
    delivery_status: str
    grading_status: str
    revision: int
    created_at: datetime
    updated_at: datetime


class SessionDetail(BaseModel):
    id: int
    assessment_id: int
    assessment_title: Optional[str] = None
    version_id: int
    version_no: int
    subject_id: int
    name: str
    delivery_status: str
    grading_status: str
    opens_at: Optional[datetime] = None
    closes_at: Optional[datetime] = None
    attempt_limit: Optional[int] = None
    revision: int
    created_at: datetime
    updated_at: datetime
    total_score: Optional[Decimal] = None
    item_count: Optional[int] = None
    items: List[AssessmentItemRead] = Field(default_factory=list)
    participants: List[ParticipationRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 追加式评分
# --------------------------------------------------------------------------- #
class GradeItemInput(BaseModel):
    item_id: int
    score: Optional[Decimal] = None
    outcome: Optional[str] = None
    grading_method: Optional[str] = None
    feedback: Optional[Any] = None


class GradeAppendRequest(BaseModel):
    """按 attempt 追加评分;expected_revision 乐观锁,batch_id 幂等重试键。"""
    expected_revision: int
    batch_id: Optional[str] = Field(default=None, max_length=64)
    items: List[GradeItemInput] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def _non_empty(cls, v: List[GradeItemInput]) -> List[GradeItemInput]:
        if not v:
            raise ValueError("至少需要一条评分项")
        return v


class AttemptGradeRow(BaseModel):
    item_id: int
    item_key: str
    max_score: Decimal
    response_id: Optional[int] = None
    score: Optional[Decimal] = None
    outcome: Optional[str] = None
    grade_revision: int
    status: str


class AttemptGradeResult(BaseModel):
    attempt_id: int
    participation_id: int
    attempt_no: int
    status: str
    revision: int
    total_score: Optional[Decimal] = None
    max_score: Optional[Decimal] = None
    answered_count: int
    graded_count: int
    grades: List[AttemptGradeRow] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# gradebook / 统计
# --------------------------------------------------------------------------- #
class GradebookScore(BaseModel):
    item_id: int
    score: Optional[Decimal] = None
    outcome: Optional[str] = None


class GradebookRow(BaseModel):
    participation_id: int
    participant_key: str
    display_name: Optional[str] = None
    identifier: Optional[str] = None
    attendance_status: str
    participation_status: str
    attempt_id: Optional[int] = None
    attempt_revision: int
    attempt_status: Optional[str] = None
    total_score: Optional[Decimal] = None
    graded_count: int
    scores: List[GradebookScore] = Field(default_factory=list)


class GradebookRead(BaseModel):
    session_id: int
    grading_status: str
    delivery_status: str
    revision: int
    total_score: Optional[Decimal] = None
    item_count: int
    items: List[AssessmentItemRead] = Field(default_factory=list)
    participants: List[GradebookRow] = Field(default_factory=list)
    page: int
    page_size: int
    total: int


class ItemStatistic(BaseModel):
    item_id: int
    item_key: str
    position: int
    max_score: Decimal
    graded_count: int
    average_score: Optional[Decimal] = None
    min_score: Optional[Decimal] = None
    max_score_awarded: Optional[Decimal] = None
    full_marks_count: int
    incorrect_count: int = 0
    # 失分率:未拿满分的比例(相对已评分作答);无评分时为 None。
    error_rate: Optional[Decimal] = None


class ItemStatisticsRead(BaseModel):
    session_id: int
    grading_status: str
    participation_count: int
    items: List[ItemStatistic] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 成绩册 Excel 导入
# --------------------------------------------------------------------------- #
class ScoreImportError(BaseModel):
    """单行级别的导入错误(可聚合)。"""
    row: int
    field: str
    message: str


class ScoreImportPreview(BaseModel):
    session_id: int
    valid: bool
    total_rows: int
    changed_rows: int
    changed_scores: int
    unchanged_rows: int
    errors: List[ScoreImportError] = Field(default_factory=list)


class ScoreImportResult(BaseModel):
    session_id: int
    batch_id: Optional[str] = None
    changed_rows: int
    changed_scores: int
    unchanged_rows: int
    applied_attempts: int
    # 幂等重放命中(相同 batch_id + 同文件)时为 True,表示未再次写库。
    replayed: bool = False
