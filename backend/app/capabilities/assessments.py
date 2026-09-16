"""通用评测 (Assessment) 域能力 —— 第二期纵向切片的唯一业务入口。

三段式 `load → authorize → execute`:`load` 做学科存在性前置(不可见/不存在的学科统一
404),`authorize` 按学科作用域判权(VIEW_ASSESSMENT / MANAGE_ASSESSMENT / EDIT_SCORE),
`execute` 委托 `services.assessment_service` / `crud_assessment` 完成工作单元并自行 commit。

判权语义:
- 读(名册/评测/投放/gradebook/统计)→ VIEW_ASSESSMENT。
- 管理(建学生/班级/替换成员/从组稿创建评测)→ MANAGE_ASSESSMENT。
- 录分(开始/定稿/追加成绩)→ EDIT_SCORE。

跨学科定位失败在 service/crud 的 scoped 查询里回落为 NotFound(404,防枚举)。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app import crud
from app.core.permissions import Permission
from app.crud import crud_assessment
from app.services import assessment_service

from .base import Authz, Capability, Scope
from .context import ExecutionContext
from .errors import NotFound
from .registry import register


async def _ensure_subject(ctx: ExecutionContext, subject_id: int) -> None:
    if not await crud.subject.get(ctx.db, id=subject_id):
        raise NotFound("Subject not found")


# --------------------------------------------------------------------------- #
# 输入模型
# --------------------------------------------------------------------------- #
class SubjectScopedInput(BaseModel):
    subject_id: int


class StudentCreateInput(SubjectScopedInput):
    student_no: str
    name: str
    user_id: Optional[int] = None


class StudentListInput(SubjectScopedInput):
    keyword: Optional[str] = None
    page: int = 1
    page_size: int = 50


class ClassroomCreateInput(SubjectScopedInput):
    name: str


class ClassroomListInput(SubjectScopedInput):
    pass


class ClassroomStudentsListInput(SubjectScopedInput):
    classroom_id: int


class ClassroomMembersReplaceInput(SubjectScopedInput):
    classroom_id: int
    student_ids: List[int] = Field(default_factory=list)


class AssessmentCreateInput(SubjectScopedInput):
    title: str
    composition_version_id: int
    classroom_id: int
    session_name: Optional[str] = None


class AssessmentListInput(SubjectScopedInput):
    status: Optional[str] = None


class AssessmentRefInput(SubjectScopedInput):
    assessment_id: int


class SessionListInput(SubjectScopedInput):
    grading_status: Optional[str] = None
    assessment_id: Optional[int] = None


class SessionRefInput(SubjectScopedInput):
    session_id: int


class GradebookInput(SessionRefInput):
    page: int = 1
    page_size: int = 50


class GradeAppendInput(SubjectScopedInput):
    attempt_id: int
    expected_revision: int
    batch_id: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


class ExportGradebookInput(SessionRefInput):
    pass


class PreviewGradeImportInput(SessionRefInput):
    file_bytes: bytes


class ApplyGradeImportInput(SessionRefInput):
    file_bytes: bytes
    batch_id: Optional[str] = None


# --------------------------------------------------------------------------- #
# 名册
# --------------------------------------------------------------------------- #
@register
class CreateStudent(Capability[StudentCreateInput, Any]):
    name = "assessment.create_student"
    description = "在学科名册下新建学生档案。"
    input_model = StudentCreateInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: StudentCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(self, ctx: ExecutionContext, inp: StudentCreateInput, target: Any) -> Any:
        return await assessment_service.create_student(
            ctx.db,
            subject_id=inp.subject_id,
            student_no=inp.student_no,
            name=inp.name,
            user_id=inp.user_id,
            actor=ctx.actor,
        )


@register
class ListStudents(Capability[StudentListInput, Dict[str, Any]]):
    name = "assessment.list_students"
    description = "分页查询学科名册中的学生。"
    input_model = StudentListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: StudentListInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: StudentListInput, target: Any
    ) -> Dict[str, Any]:
        students, total = await crud_assessment.assessment.list_students(
            ctx.db,
            subject_id=inp.subject_id,
            keyword=inp.keyword,
            page=inp.page,
            page_size=inp.page_size,
        )
        return {
            "items": students,
            "total": total,
            "page": inp.page,
            "page_size": inp.page_size,
        }


@register
class CreateClassroom(Capability[ClassroomCreateInput, Any]):
    name = "assessment.create_classroom"
    description = "在学科下新建班级。"
    input_model = ClassroomCreateInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ClassroomCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(self, ctx: ExecutionContext, inp: ClassroomCreateInput, target: Any) -> Any:
        return await assessment_service.create_classroom(
            ctx.db, subject_id=inp.subject_id, name=inp.name, actor=ctx.actor
        )


@register
class ListClassrooms(Capability[ClassroomListInput, Any]):
    name = "assessment.list_classrooms"
    description = "列出学科下的班级。"
    input_model = ClassroomListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ClassroomListInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(self, ctx: ExecutionContext, inp: ClassroomListInput, target: Any) -> Any:
        return await crud_assessment.assessment.list_classrooms(
            ctx.db, subject_id=inp.subject_id
        )


@register
class ListClassroomStudents(Capability[ClassroomStudentsListInput, Any]):
    name = "assessment.list_classroom_students"
    description = "列出某个班级的学生。"
    input_model = ClassroomStudentsListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ClassroomStudentsListInput) -> Any:
        await _ensure_subject(ctx, inp.subject_id)
        classroom = await crud_assessment.assessment.get_classroom(
            ctx.db, classroom_id=inp.classroom_id
        )
        if classroom is None or classroom.subject_id != inp.subject_id:
            raise NotFound("Classroom not found")
        return classroom

    async def execute(
        self, ctx: ExecutionContext, inp: ClassroomStudentsListInput, target: Any
    ) -> Any:
        return await crud_assessment.assessment.list_classroom_students(
            ctx.db, classroom_id=inp.classroom_id
        )


@register
class ReplaceClassroomMembers(Capability[ClassroomMembersReplaceInput, Any]):
    name = "assessment.replace_classroom_members"
    description = "整体替换班级成员名单。"
    input_model = ClassroomMembersReplaceInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ClassroomMembersReplaceInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ClassroomMembersReplaceInput, target: Any
    ) -> Any:
        return await assessment_service.replace_classroom_members(
            ctx.db,
            subject_id=inp.subject_id,
            classroom_id=inp.classroom_id,
            student_ids=inp.student_ids,
            actor=ctx.actor,
        )


# --------------------------------------------------------------------------- #
# 评测身份 / 版本(从组稿定稿创建)
# --------------------------------------------------------------------------- #
@register
class CreateAssessment(Capability[AssessmentCreateInput, Dict[str, Any]]):
    name = "assessment.create_assessment"
    description = "从一个 shared 组稿定稿版本 + 班级原子创建评测(身份 + v1 + 投放)。"
    input_model = AssessmentCreateInput
    authz = Authz.PERMISSION
    permission = Permission.MANAGE_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: AssessmentCreateInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: AssessmentCreateInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.create_from_composition(
            ctx.db,
            subject_id=inp.subject_id,
            composition_version_id=inp.composition_version_id,
            classroom_id=inp.classroom_id,
            title=inp.title,
            session_name=inp.session_name,
            actor=ctx.actor,
        )


@register
class ListAssessments(Capability[AssessmentListInput, Any]):
    name = "assessment.list_assessments"
    description = "列出学科下的评测身份。"
    input_model = AssessmentListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: AssessmentListInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(self, ctx: ExecutionContext, inp: AssessmentListInput, target: Any) -> Any:
        return await crud_assessment.assessment.list_assessments(
            ctx.db, subject_id=inp.subject_id, status=inp.status
        )


@register
class GetAssessment(Capability[AssessmentRefInput, Dict[str, Any]]):
    name = "assessment.get_assessment"
    description = "查看评测身份详情(含版本与当前条目)。"
    input_model = AssessmentRefInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: AssessmentRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: AssessmentRefInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.get_assessment_detail(
            ctx.db, subject_id=inp.subject_id, assessment_id=inp.assessment_id
        )


# --------------------------------------------------------------------------- #
# 投放 session
# --------------------------------------------------------------------------- #
@register
class ListSessions(Capability[SessionListInput, Any]):
    name = "assessment.list_sessions"
    description = "列出学科下的评测投放。"
    input_model = SessionListInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: SessionListInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(self, ctx: ExecutionContext, inp: SessionListInput, target: Any) -> Any:
        return await assessment_service.list_sessions(
            ctx.db,
            subject_id=inp.subject_id,
            grading_status=inp.grading_status,
            assessment_id=inp.assessment_id,
        )


@register
class GetSession(Capability[SessionRefInput, Dict[str, Any]]):
    name = "assessment.get_session"
    description = "查看评测投放详情(冻结条目 + 参与者 + attempts)。"
    input_model = SessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: SessionRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: SessionRefInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.get_session_detail(
            ctx.db, subject_id=inp.subject_id, session_id=inp.session_id
        )


@register
class StartGrading(Capability[SessionRefInput, Dict[str, Any]]):
    name = "assessment.start_grading"
    description = "评分状态 not_started → in_progress。"
    input_model = SessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_SCORE
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: SessionRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: SessionRefInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.start_grading(
            ctx.db, subject_id=inp.subject_id, session_id=inp.session_id, actor=ctx.actor
        )


@register
class FinalizeGrading(Capability[SessionRefInput, Dict[str, Any]]):
    name = "assessment.finalize_grading"
    description = "评分状态 in_progress → finalized;要求全部应评参与者已完整评分。"
    input_model = SessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_SCORE
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: SessionRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: SessionRefInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.finalize_grading(
            ctx.db, subject_id=inp.subject_id, session_id=inp.session_id, actor=ctx.actor
        )


@register
class GetGradebook(Capability[GradebookInput, Dict[str, Any]]):
    name = "assessment.get_gradebook"
    description = "分页读取投放的成绩册矩阵。"
    input_model = GradebookInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: GradebookInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: GradebookInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.get_gradebook(
            ctx.db,
            subject_id=inp.subject_id,
            session_id=inp.session_id,
            page=inp.page,
            page_size=inp.page_size,
        )


@register
class ItemStatistics(Capability[SessionRefInput, Dict[str, Any]]):
    name = "assessment.item_statistics"
    description = "按条目聚合投放的评分统计(分母只计已评分的应评作答)。"
    input_model = SessionRefInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: SessionRefInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: SessionRefInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.get_item_statistics(
            ctx.db, subject_id=inp.subject_id, session_id=inp.session_id
        )


# --------------------------------------------------------------------------- #
# 追加式评分
# --------------------------------------------------------------------------- #
@register
class AppendGrades(Capability[GradeAppendInput, Dict[str, Any]]):
    name = "assessment.append_grades"
    description = "对某个 attempt 追加式录分(乐观锁 + 幂等 batch)。"
    input_model = GradeAppendInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_SCORE
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: GradeAppendInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: GradeAppendInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.append_grades(
            ctx.db,
            subject_id=inp.subject_id,
            attempt_id=inp.attempt_id,
            expected_revision=inp.expected_revision,
            batch_id=inp.batch_id,
            items=inp.items,
            actor=ctx.actor,
        )


# --------------------------------------------------------------------------- #
# 成绩册 Excel:导出 / 预览 / 应用
# --------------------------------------------------------------------------- #
@register
class ExportGradebook(Capability[ExportGradebookInput, bytes]):
    name = "assessment.export_gradebook"
    description = "导出教师成绩册 Excel(当前最新评分快照)。"
    input_model = ExportGradebookInput
    authz = Authz.PERMISSION
    permission = Permission.VIEW_ASSESSMENT
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: ExportGradebookInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ExportGradebookInput, target: Any
    ) -> bytes:
        return await assessment_service.export_gradebook(
            ctx.db, subject_id=inp.subject_id, session_id=inp.session_id
        )


@register
class PreviewGradeImport(Capability[PreviewGradeImportInput, Dict[str, Any]]):
    name = "assessment.preview_grade_import"
    description = "预览成绩册导入:验证结构、聚合行错误、计算变更统计,不写库。"
    input_model = PreviewGradeImportInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_SCORE
    scope = Scope.SUBJECT
    mutating = False

    async def load(self, ctx: ExecutionContext, inp: PreviewGradeImportInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: PreviewGradeImportInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.preview_grade_import(
            ctx.db,
            subject_id=inp.subject_id,
            session_id=inp.session_id,
            file_bytes=inp.file_bytes,
        )


@register
class ApplyGradeImport(Capability[ApplyGradeImportInput, Dict[str, Any]]):
    name = "assessment.apply_grade_import"
    description = "应用成绩册导入:任一错误全拒绝,单事务原子应用,batch+sha256 幂等。"
    input_model = ApplyGradeImportInput
    authz = Authz.PERMISSION
    permission = Permission.EDIT_SCORE
    scope = Scope.SUBJECT
    mutating = True

    async def load(self, ctx: ExecutionContext, inp: ApplyGradeImportInput) -> None:
        await _ensure_subject(ctx, inp.subject_id)

    async def execute(
        self, ctx: ExecutionContext, inp: ApplyGradeImportInput, target: Any
    ) -> Dict[str, Any]:
        return await assessment_service.apply_grade_import(
            ctx.db,
            subject_id=inp.subject_id,
            session_id=inp.session_id,
            file_bytes=inp.file_bytes,
            batch_id=inp.batch_id,
            actor=ctx.actor,
        )

