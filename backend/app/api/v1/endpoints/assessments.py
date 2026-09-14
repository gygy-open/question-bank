"""成绩录入 (Assessment) API —— 第二期纵向切片。

Subject 强上下文路由:/subjects/{subject_id}/...(学生、班级、考试)。
业务逻辑全部经 capability 入口,端点只做请求收敛与响应投影。
"""
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse

from app import capabilities, models
from app.api import deps
from app.capabilities import assessments as assessment_caps
from app.schemas.assessment import (
    ClassroomCreateRequest,
    ClassroomMembersReplaceRequest,
    ClassroomRead,
    ExamResultRead,
    ExamSessionCreateRequest,
    ExamSessionDetail,
    ExamSessionRead,
    GradebookRead,
    ScoreSaveRequest,
    ScoreImportPreview,
    ScoreImportResult,
    StudentCreateRequest,
    StudentPage,
    StudentRead,
)

router = APIRouter()
MAX_IMPORT_SIZE = 5 * 1024 * 1024
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _read_xlsx(file: UploadFile) -> bytes:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式的文件")
    content = await file.read()
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，请确保文件小于 5MB")
    return content


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
# 考试创建 / 详情
# --------------------------------------------------------------------------- #
@router.get("/{subject_id}/exam-sessions", response_model=List[ExamSessionRead])
async def list_exam_sessions(
    subject_id: int,
    db: deps.SessionDep,
    status_filter: Optional[str] = Query(default=None, alias="status"),
    classroom_id: Optional[int] = Query(default=None),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.list_exam_sessions",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ExamSessionListInput(
            subject_id=subject_id, status=status_filter, classroom_id=classroom_id
        ),
    )


@router.post(
    "/{subject_id}/exam-sessions",
    response_model=ExamSessionDetail,
    status_code=status.HTTP_201_CREATED,
)
async def create_exam_session(
    subject_id: int,
    payload: ExamSessionCreateRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.create_exam_session",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ExamSessionCreateInput(
            subject_id=subject_id,
            composition_version_id=payload.composition_version_id,
            classroom_id=payload.classroom_id,
            name=payload.name,
        ),
    )


@router.get(
    "/{subject_id}/exam-sessions/{exam_session_id}",
    response_model=ExamSessionDetail,
)
async def get_exam_session(
    subject_id: int,
    exam_session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.get_exam_session",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ExamSessionRefInput(
            subject_id=subject_id,
            exam_session_id=exam_session_id,
        ),
    )


# --------------------------------------------------------------------------- #
# 考试状态流转
# --------------------------------------------------------------------------- #
@router.post(
    "/{subject_id}/exam-sessions/{exam_session_id}/start-recording",
    response_model=ExamSessionDetail,
)
async def start_recording(
    subject_id: int,
    exam_session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.start_recording",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ExamSessionRefInput(
            subject_id=subject_id, exam_session_id=exam_session_id
        ),
    )


@router.post(
    "/{subject_id}/exam-sessions/{exam_session_id}/lock",
    response_model=ExamSessionDetail,
)
async def lock_exam_session(
    subject_id: int,
    exam_session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.lock_exam_session",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ExamSessionRefInput(
            subject_id=subject_id, exam_session_id=exam_session_id
        ),
    )


# --------------------------------------------------------------------------- #
# gradebook 读取 / 逐题录分
# --------------------------------------------------------------------------- #
@router.get("/{subject_id}/exam-sessions/{exam_session_id}/gradebook.xlsx")
async def export_gradebook(
    subject_id: int,
    exam_session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    content = await capabilities.run(
        "assessment.export_gradebook",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ExamSessionRefInput(
            subject_id=subject_id, exam_session_id=exam_session_id
        ),
    )
    return StreamingResponse(
        iter([content]),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="exam_{exam_session_id}_scores.xlsx"'
        },
    )


@router.post(
    "/{subject_id}/exam-sessions/{exam_session_id}/score-imports/preview",
    response_model=ScoreImportPreview,
)
async def preview_score_import(
    subject_id: int,
    exam_session_id: int,
    db: deps.SessionDep,
    file: UploadFile = File(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    content = await _read_xlsx(file)
    return await capabilities.run(
        "assessment.preview_score_import",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ScoreImportInput(
            subject_id=subject_id,
            exam_session_id=exam_session_id,
            file_bytes=content,
        ),
    )


@router.post(
    "/{subject_id}/exam-sessions/{exam_session_id}/score-imports/apply",
    response_model=ScoreImportResult,
)
async def apply_score_import(
    subject_id: int,
    exam_session_id: int,
    db: deps.SessionDep,
    batch_id: str = Form(..., min_length=1, max_length=64),
    file: UploadFile = File(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    content = await _read_xlsx(file)
    return await capabilities.run(
        "assessment.apply_score_import",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ScoreImportApplyInput(
            subject_id=subject_id,
            exam_session_id=exam_session_id,
            file_bytes=content,
            batch_id=batch_id,
        ),
    )


@router.get(
    "/{subject_id}/exam-sessions/{exam_session_id}/gradebook",
    response_model=GradebookRead,
)
async def get_gradebook(
    subject_id: int,
    exam_session_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.get_gradebook",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.ExamSessionRefInput(
            subject_id=subject_id, exam_session_id=exam_session_id
        ),
    )


@router.patch(
    "/{subject_id}/exam-sessions/{exam_session_id}/results/{result_id}",
    response_model=ExamResultRead,
)
async def save_scores(
    subject_id: int,
    exam_session_id: int,
    result_id: int,
    payload: ScoreSaveRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await capabilities.run(
        "assessment.save_scores",
        deps.api_context(db, current_user, subject_id=subject_id),
        assessment_caps.SaveScoresInput(
            subject_id=subject_id,
            exam_session_id=exam_session_id,
            result_id=result_id,
            expected_revision=payload.expected_revision,
            batch_id=payload.batch_id,
            items=[
                assessment_caps.ScoreItemInput(
                    exam_question_id=item.exam_question_id, score=item.score
                )
                for item in payload.items
            ],
        ),
    )

