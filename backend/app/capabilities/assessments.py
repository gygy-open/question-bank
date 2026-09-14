"""成绩录入 (Assessment) 域能力 —— 第二期纵向切片。

覆盖:学生/班级名册、考试创建与详情、考试状态流转(开始录入 / 锁定)、
gradebook 读取与逐题录分。

鉴权显式声明,均为 Scope.SUBJECT:
- 读取(详情 / 名册 / gradebook):VIEW_ASSESSMENT
- 创建学生/班级、改名单、状态流转:MANAGE_ASSESSMENT
- 保存成绩:EDIT_SCORE
不进入 UNGATED_ALLOWLIST。
"""
from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app import crud
from app.core.permissions import Permission
from app.crud import crud_assessment
from app.models.assessment import Classroom, ExamSession, Student
from app.services import assessment_service

from .base import Authz, Capability, Scope
from .context import ExecutionContext
from .errors import NotFound
from .registry import register


class ExamSessionCreateInput(BaseModel):
    subject_id: int
    composition_version_id: int
    classroom_id: int
    name: str


class ExamSessionRefInput(BaseModel):
    subject_id: int
    exam_session_id: int


class ExamSessionListInput(BaseModel):
    subject_id: int
    status: Optional[str] = None
    classroom_id: Optional[int] = None


class StudentCreateInput(BaseModel):
    subject_id: int
    student_no: str
    name: str
    user_id: Optional[int] = None


class StudentListInput(BaseModel):
    subject_id: int
    keyword: Optional[str] = None
    page: int = 1
    page_size: int = 50


class ClassroomCreateInput(BaseModel):
    subject_id: int
    name: str


class ClassroomListInput(BaseModel):
    subject_id: int


class ClassroomStudentsListInput(BaseModel):
    subject_id: int
    classroom_id: int


class ClassroomMembersReplaceInput(BaseModel):
    subject_id: int
    classroom_id: int
    student_ids: List[int] = Field(default_factory=list)


class ScoreItemInput(BaseModel):
    exam_question_id: int
    score: Optional[Any] = None


class SaveScoresInput(BaseModel):
    subject_id: int
    exam_session_id: int
    result_id: int
    expected_revision: int
    batch_id: Optional[str] = None
    items: List[ScoreItemInput] = Field(default_factory=list)


class ScoreImportInput(BaseModel):
    subject_id: int
    exam_session_id: int
    file_bytes: bytes


class ScoreImportApplyInput(ScoreImportInput):
    batch_id: str = Field(min_length=1, max_length=64)


async def _ensure_subject(ctx: ExecutionContext, subject_id: int) -> None:
    if not await crud.subject.get(ctx.db, id=subject_id):
        raise NotFound("Subject not found")


@register
class CreateExamSession(Capability[ExamSessionCreateInput, ExamSession]):
    name = "assessment.create_exam_session"
    description = "从一个共享组稿定稿版本与班级创建一场 draft 考试并冻结题目/参与者。"
    input_model = ExamSessionCreateInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ExamSessionCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ExamSessionCreateInput, target: Any
    ) -> ExamSession:
        return await assessment_service.create_exam_session(
            ctx.db,
            subject_id=inp.subject_id,
            composition_version_id=inp.composition_version_id,
            classroom_id=inp.classroom_id,
            name=inp.name,
            actor=ctx.actor,
        )


@register
class GetExamSession(Capability[ExamSessionRefInput, ExamSession]):
    name = "assessment.get_exam_session"
    description = "按学科强上下文读取考试详情(题目清单与参与者快照)。"
    input_model = ExamSessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ExamSessionRefInput) -> ExamSession:
        await _ensure_subject(ctx, inp.subject_id)
        session = await crud_assessment.assessment.get_session_detail(
            ctx.db, exam_session_id=inp.exam_session_id, subject_id=inp.subject_id
        )
        if session is None:
            raise NotFound("Exam session not found")
        return session

    async def execute(
        self, ctx: ExecutionContext, inp: ExamSessionRefInput, target: ExamSession
    ) -> ExamSession:
        return target


@register
class ListExamSessions(Capability[ExamSessionListInput, list]):
    name = "assessment.list_exam_sessions"
    description = "按学科列出考试(可选 status / classroom_id 过滤),按创建时间倒序。"
    input_model = ExamSessionListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ExamSessionListInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ExamSessionListInput, target: Any
    ) -> list:
        return await crud_assessment.assessment.list_sessions(
            ctx.db,
            subject_id=inp.subject_id,
            status=inp.status,
            classroom_id=inp.classroom_id,
        )
@register
class CreateStudent(Capability[StudentCreateInput, Student]):
    name = "assessment.create_student"
    description = "在学科下创建学生档案(学号学科内唯一,可绑定系统用户)。"
    input_model = StudentCreateInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: StudentCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: StudentCreateInput, target: Any
    ) -> Student:
        return await assessment_service.create_student(
            ctx.db,
            subject_id=inp.subject_id,
            student_no=inp.student_no,
            name=inp.name,
            user_id=inp.user_id,
            actor=ctx.actor,
        )


@register
class ListStudents(Capability[StudentListInput, dict]):
    name = "assessment.list_students"
    description = "按学科分页/搜索学生名册。"
    input_model = StudentListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: StudentListInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: StudentListInput, target: Any
    ) -> dict:
        items, total = await crud_assessment.assessment.list_students(
            ctx.db,
            subject_id=inp.subject_id,
            keyword=inp.keyword,
            page=inp.page,
            page_size=inp.page_size,
        )
        return {
            "items": items,
            "total": total,
            "page": inp.page,
            "page_size": inp.page_size,
        }


@register
class CreateClassroom(Capability[ClassroomCreateInput, Classroom]):
    name = "assessment.create_classroom"
    description = "在学科下创建班级/群组。"
    input_model = ClassroomCreateInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ClassroomCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ClassroomCreateInput, target: Any
    ) -> Classroom:
        return await assessment_service.create_classroom(
            ctx.db, subject_id=inp.subject_id, name=inp.name, actor=ctx.actor
        )


@register
class ListClassrooms(Capability[ClassroomListInput, list]):
    name = "assessment.list_classrooms"
    description = "按学科列出班级。"
    input_model = ClassroomListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ClassroomListInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ClassroomListInput, target: Any
    ) -> list:
        return await crud_assessment.assessment.list_classrooms(
            ctx.db, subject_id=inp.subject_id
        )


@register
class ListClassroomStudents(Capability[ClassroomStudentsListInput, list]):
    name = "assessment.list_classroom_students"
    description = "读取某班级当前成员的学生名册(跨学科班级 404)。"
    input_model = ClassroomStudentsListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(
        self, ctx: ExecutionContext, inp: ClassroomStudentsListInput
    ) -> Classroom:
        await _ensure_subject(ctx, inp.subject_id)
        classroom = await crud_assessment.assessment.get_classroom(
            ctx.db, classroom_id=inp.classroom_id
        )
        if classroom is None or classroom.subject_id != inp.subject_id:
            raise NotFound("Classroom not found")
        return classroom

    async def execute(
        self, ctx: ExecutionContext, inp: ClassroomStudentsListInput, target: Classroom
    ) -> list:
        return await crud_assessment.assessment.list_classroom_students(
            ctx.db, classroom_id=inp.classroom_id
        )


@register
class ReplaceClassroomMembers(Capability[ClassroomMembersReplaceInput, list]):
    name = "assessment.replace_classroom_members"
    description = "整体替换班级成员(原子;去重;跨学科学生 422,班级不存在/跨学科 404)。"
    input_model = ClassroomMembersReplaceInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ClassroomMembersReplaceInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ClassroomMembersReplaceInput, target: Any
    ) -> list:
        return await assessment_service.replace_classroom_members(
            ctx.db,
            subject_id=inp.subject_id,
            classroom_id=inp.classroom_id,
            student_ids=inp.student_ids,
            actor=ctx.actor,
        )


# --------------------------------------------------------------------------- #
# 考试状态流转
# --------------------------------------------------------------------------- #
@register
class StartRecording(Capability[ExamSessionRefInput, ExamSession]):
    name = "assessment.start_recording"
    description = "draft → recording(要求至少一个参与者与一个题目)。"
    input_model = ExamSessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ExamSessionRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ExamSessionRefInput, target: Any
    ) -> ExamSession:
        return await assessment_service.start_recording(
            ctx.db,
            subject_id=inp.subject_id,
            exam_session_id=inp.exam_session_id,
            actor=ctx.actor,
        )


@register
class LockExamSession(Capability[ExamSessionRefInput, ExamSession]):
    name = "assessment.lock_exam_session"
    description = "recording → locked(要求所有非缺考参与者每题均已录分)。"
    input_model = ExamSessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ExamSessionRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ExamSessionRefInput, target: Any
    ) -> ExamSession:
        return await assessment_service.lock_exam_session(
            ctx.db,
            subject_id=inp.subject_id,
            exam_session_id=inp.exam_session_id,
            actor=ctx.actor,
        )


# --------------------------------------------------------------------------- #
# gradebook 读取 / 逐题录分
# --------------------------------------------------------------------------- #
@register
class GetGradebook(Capability[ExamSessionRefInput, dict]):
    name = "assessment.get_gradebook"
    description = "读取单场考试的 gradebook 矩阵(题目列 + 每个参与者逐题成绩)。"
    input_model = ExamSessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ExamSessionRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ExamSessionRefInput, target: Any
    ) -> dict:
        return await assessment_service.get_gradebook(
            ctx.db, subject_id=inp.subject_id, exam_session_id=inp.exam_session_id
        )


@register
class ExportGradebook(Capability[ExamSessionRefInput, bytes]):
    name = "assessment.export_gradebook"
    description = "导出带考试、题目和成绩 revision 元数据的 Excel 成绩表。"
    input_model = ExamSessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ExamSessionRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ExamSessionRefInput, target: Any
    ) -> bytes:
        return await assessment_service.export_gradebook(
            ctx.db, subject_id=inp.subject_id, exam_session_id=inp.exam_session_id
        )


@register
class PreviewScoreImport(Capability[ScoreImportInput, dict]):
    name = "assessment.preview_score_import"
    description = "只读预检 Excel 成绩文件，不修改成绩。"
    input_model = ScoreImportInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_SCORE
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ScoreImportInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ScoreImportInput, target: Any
    ) -> dict:
        return await assessment_service.preview_score_import(
            ctx.db,
            subject_id=inp.subject_id,
            exam_session_id=inp.exam_session_id,
            file_bytes=inp.file_bytes,
        )


@register
class ApplyScoreImport(Capability[ScoreImportApplyInput, dict]):
    name = "assessment.apply_score_import"
    description = "原子应用 Excel 成绩，按文件摘要和 batch_id 保证幂等。"
    input_model = ScoreImportApplyInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_SCORE
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ScoreImportApplyInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ScoreImportApplyInput, target: Any
    ) -> dict:
        return await assessment_service.apply_score_import(
            ctx.db,
            subject_id=inp.subject_id,
            exam_session_id=inp.exam_session_id,
            file_bytes=inp.file_bytes,
            batch_id=inp.batch_id,
            actor=ctx.actor,
        )


@register
class SaveScores(Capability[SaveScoresInput, dict]):
    name = "assessment.save_scores"
    description = "按参与者逐题保存成绩(乐观锁 revision + batch_id 幂等)。"
    input_model = SaveScoresInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_SCORE
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: SaveScoresInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: SaveScoresInput, target: Any
    ) -> dict:
        return await assessment_service.save_scores(
            ctx.db,
            subject_id=inp.subject_id,
            exam_session_id=inp.exam_session_id,
            result_id=inp.result_id,
            expected_revision=inp.expected_revision,
            batch_id=inp.batch_id,
            items=[item.model_dump() for item in inp.items],
            actor=ctx.actor,
        )

