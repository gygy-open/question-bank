"""成绩录入 (Assessment) API —— 第二期纵向切片。

Subject 强上下文路由:/subjects/{subject_id}/...(学生、班级、评测、投放、录分)。
业务逻辑全部经 capability 入口,端点只做请求收敛与响应投影。
"""

from typing import Any, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app import capabilities, models
from app.api import deps
from app.capabilities import assessments as assessment_caps
from app.schemas.assessment import (
    AssessmentCreateRequest,
    AssessmentDetail,
    AssessmentRead,
    AttemptGradeResult,
    ClassroomCreateRequest,
    ClassroomMembersReplaceRequest,
    ClassroomRead,
    GradeAppendRequest,
    GradebookRead,
    ItemStatisticsRead,
    ScoreImportPreview,
    ScoreImportResult,
    SessionDetail,
    SessionRead,
    StudentCreateRequest,
    StudentPage,
    StudentRead,
)

router = APIRouter()

MAX_IMPORT_SIZE = 5 * 1024 * 1024  # 5 MB


# --------------------------------------------------------------------------- #
# 学生名册
# --------------------------------------------------------------------------- #
@router.post(
    "/{subject_id}/students",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_student(
    subject_id: int,
    payload: StudentCreateRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.create_student",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.StudentCreateInput(
            subject_id=subject_id,
            student_no=payload.student_no,
            name=payload.name,
            user_id=payload.user_id,
        ),
    )


@router.get("/{subject_id}/students", response_model=StudentPage)
async def list_students(
    subject_id: int,
    db: deps.SessionDep,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.list_students",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.StudentListInput(
            subject_id=subject_id, keyword=keyword, page=page, page_size=page_size
        ),
    )


# --------------------------------------------------------------------------- #
# 班级名册
# --------------------------------------------------------------------------- #
@router.post(
    "/{subject_id}/classrooms",
    response_model=ClassroomRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_classroom(
    subject_id: int,
    payload: ClassroomCreateRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.create_classroom",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ClassroomCreateInput(subject_id=subject_id, name=payload.name),
    )


@router.get("/{subject_id}/classrooms", response_model=List[ClassroomRead])
async def list_classrooms(
    subject_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.list_classrooms",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ClassroomListInput(subject_id=subject_id),
    )


@router.get(
    "/{subject_id}/classrooms/{classroom_id}/students",
    response_model=List[StudentRead],
)
async def list_classroom_students(
    subject_id: int,
    classroom_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.list_classroom_students",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ClassroomStudentsListInput(
            subject_id=subject_id, classroom_id=classroom_id
        ),
    )


@router.put(
    "/{subject_id}/classrooms/{classroom_id}/students",
    response_model=List[StudentRead],
)
async def replace_classroom_members(
    subject_id: int,
    classroom_id: int,
    payload: ClassroomMembersReplaceRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.replace_classroom_members",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ClassroomMembersReplaceInput(
            subject_id=subject_id,
            classroom_id=classroom_id,
            student_ids=payload.student_ids,
        ),
    )


# --------------------------------------------------------------------------- #
# 评测身份(从组稿定稿创建)/ 列表 / 详情
# --------------------------------------------------------------------------- #
@router.get("/{subject_id}/assessments", response_model=List[AssessmentRead])
async def list_assessments(
    subject_id: int,
    db: deps.SessionDep,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.list_assessments",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.AssessmentListInput(
            subject_id=subject_id, status=status_filter
        ),
    )


@router.post(
    "/{subject_id}/assessments",
    response_model=SessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_assessment(
    subject_id: int,
    payload: AssessmentCreateRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.create_assessment",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.AssessmentCreateInput(
            subject_id=subject_id,
            title=payload.title,
            composition_version_id=payload.composition_version_id,
            classroom_id=payload.classroom_id,
            session_name=payload.session_name,
        ),
    )


@router.get(
    "/{subject_id}/assessments/{assessment_id}",
    response_model=AssessmentDetail,
)
async def get_assessment(
    subject_id: int,
    assessment_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.get_assessment",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.AssessmentRefInput(
            subject_id=subject_id, assessment_id=assessment_id
        ),
    )


# --------------------------------------------------------------------------- #
# 投放 session 列表 / 详情
# --------------------------------------------------------------------------- #
@router.get("/{subject_id}/assessment-sessions", response_model=List[SessionRead])
async def list_assessment_sessions(
    subject_id: int,
    db: deps.SessionDep,
    grading_status: Optional[str] = Query(default=None),
    assessment_id: Optional[int] = Query(default=None),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.list_sessions",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.SessionListInput(
            subject_id=subject_id,
            grading_status=grading_status,
            assessment_id=assessment_id,
        ),
    )


@router.get(
    "/{subject_id}/assessment-sessions/{session_id}",
    response_model=SessionDetail,
)
async def get_assessment_session(
    subject_id: int,
    session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.get_session",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.SessionRefInput(subject_id=subject_id, session_id=session_id),
    )


# --------------------------------------------------------------------------- #
# 评分状态流转
# --------------------------------------------------------------------------- #
@router.post(
    "/{subject_id}/assessment-sessions/{session_id}/grading/start",
    response_model=SessionDetail,
)
async def start_grading(
    subject_id: int,
    session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.start_grading",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.SessionRefInput(subject_id=subject_id, session_id=session_id),
    )


@router.post(
    "/{subject_id}/assessment-sessions/{session_id}/grading/finalize",
    response_model=SessionDetail,
)
async def finalize_grading(
    subject_id: int,
    session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.finalize_grading",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.SessionRefInput(subject_id=subject_id, session_id=session_id),
    )


# --------------------------------------------------------------------------- #
# gradebook 读取 / item 统计 / 追加式录分
# --------------------------------------------------------------------------- #
@router.get(
    "/{subject_id}/assessment-sessions/{session_id}/gradebook",
    response_model=GradebookRead,
)
async def get_gradebook(
    subject_id: int,
    session_id: int,
    db: deps.SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.get_gradebook",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.GradebookInput(
            subject_id=subject_id, session_id=session_id, page=page, page_size=page_size
        ),
    )


@router.get(
    "/{subject_id}/assessment-sessions/{session_id}/item-statistics",
    response_model=ItemStatisticsRead,
)
async def get_item_statistics(
    subject_id: int,
    session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.item_statistics",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.SessionRefInput(subject_id=subject_id, session_id=session_id),
    )


@router.patch(
    "/{subject_id}/assessment-attempts/{attempt_id}/grades",
    response_model=AttemptGradeResult,
)
async def append_grades(
    subject_id: int,
    attempt_id: int,
    payload: GradeAppendRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.append_grades",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.GradeAppendInput(
            subject_id=subject_id,
            attempt_id=attempt_id,
            expected_revision=payload.expected_revision,
            batch_id=payload.batch_id,
            items=[item.model_dump() for item in payload.items],
        ),
    )


# --------------------------------------------------------------------------- #
# 成绩册 Excel:导出 / 预览 / 应用
# --------------------------------------------------------------------------- #
@router.get("/{subject_id}/assessment-sessions/{session_id}/gradebook.xlsx")
async def export_gradebook(
    subject_id: int,
    session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    content: bytes = await capabilities.run(
        "assessment.export_gradebook",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ExportGradebookInput(
            subject_id=subject_id, session_id=session_id
        ),
    )
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="gradebook_session_{session_id}.xlsx"'
            )
        },
    )


async def _read_import_file(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式的文件")
    content = await file.read()
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，请确保文件小于 5MB")
    return content


@router.post(
    "/{subject_id}/assessment-sessions/{session_id}/grade-imports/preview",
    response_model=ScoreImportPreview,
)
async def preview_grade_import(
    subject_id: int,
    session_id: int,
    db: deps.SessionDep,
    file: UploadFile = File(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    content = await _read_import_file(file)
    return await capabilities.run(
        "assessment.preview_grade_import",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.PreviewGradeImportInput(
            subject_id=subject_id, session_id=session_id, file_bytes=content
        ),
    )


@router.post(
    "/{subject_id}/assessment-sessions/{session_id}/grade-imports/apply",
    response_model=ScoreImportResult,
)
async def apply_grade_import(
    subject_id: int,
    session_id: int,
    db: deps.SessionDep,
    file: UploadFile = File(...),
    batch_id: Optional[str] = Form(default=None),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    content = await _read_import_file(file)
    return await capabilities.run(
        "assessment.apply_grade_import",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ApplyGradeImportInput(
            subject_id=subject_id,
            session_id=session_id,
            file_bytes=content,
            batch_id=batch_id,
        ),
    )
