"""成绩录入 (Assessment) 域 Pydantic schemas —— 第二期纵向切片。

覆盖:
- 学生/班级名册读写
- 考试创建与详情
- 考试状态流转(开始录入 / 锁定)
- gradebook 读取与逐题成绩保存
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# --------------------------------------------------------------------------- #
# 学生 / 班级名册
# --------------------------------------------------------------------------- #
class StudentCreateRequest(BaseModel):
    """在某学科下创建学生档案;user_id 可空(校内学生未必是系统用户)。"""
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
    """整体替换班级成员;student_ids 去重后原子替换。"""
    student_ids: List[int] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 考试创建 / 详情
# --------------------------------------------------------------------------- #
class ExamSessionCreateRequest(BaseModel):
    """从一个 shared 组稿定稿版本 + 班级创建 draft 考试。"""
    composition_version_id: int
    classroom_id: int
    name: str


class ExamQuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    composition_node_id: str
    q_type: str
    max_score: Decimal
    position: int


class ExamParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: Optional[int] = None
    name: str
    student_no: str
    attendance_status: str


class ExamSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    composition_version_id: int
    classroom_id: int
    name: str
    status: str
    revision: int
    total_score: Decimal
    created_at: datetime
    updated_at: datetime


class ExamSessionDetail(ExamSessionRead):
    questions: List[ExamQuestionRead] = Field(default_factory=list)
    participants: List[ExamParticipantRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# gradebook 读取
# --------------------------------------------------------------------------- #
class GradebookScoreItem(BaseModel):
    exam_question_id: int
    score: Optional[Decimal] = None


class GradebookRow(BaseModel):
    participant_id: int
    student_id: Optional[int] = None
    name: str
    student_no: str
    attendance_status: str
    result_id: int
    revision: int
    total_score: Optional[Decimal] = None
    is_complete: bool
    scores: List[GradebookScoreItem] = Field(default_factory=list)


class GradebookRead(BaseModel):
    exam_session_id: int
    status: str
    revision: int
    total_score: Decimal
    questions: List[ExamQuestionRead] = Field(default_factory=list)
    participants: List[GradebookRow] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 逐题成绩保存
# --------------------------------------------------------------------------- #
class ScoreItemInput(BaseModel):
    exam_question_id: int
    # None 表示清除该题得分。
    score: Optional[Decimal] = None


class ScoreSaveRequest(BaseModel):
    """按参与者逐题保存成绩;expected_revision 乐观锁,batch_id 幂等重试键。"""
    expected_revision: int
    batch_id: Optional[str] = Field(default=None, max_length=64)
    items: List[ScoreItemInput] = Field(default_factory=list)

    @field_validator("items")
    @classmethod
    def _non_empty(cls, v: List[ScoreItemInput]) -> List[ScoreItemInput]:
        if not v:
            raise ValueError("至少需要一条成绩项")
        return v


class ExamResultRead(BaseModel):
    """单个参与者成绩单的写后读投影。"""
    result_id: int
    participant_id: int
    revision: int
    total_score: Optional[Decimal] = None
    is_complete: bool
    scores: List[GradebookScoreItem] = Field(default_factory=list)


class ScoreImportError(BaseModel):
    row: int
    field: str
    message: str


class ScoreImportPreview(BaseModel):
    valid: bool
    changed_rows: int
    changed_scores: int
    unchanged_rows: int
    errors: List[ScoreImportError] = Field(default_factory=list)


class ScoreImportResult(BaseModel):
    batch_id: str
    updated_rows: int
    updated_scores: int
