"""导入任务 API:所有导入(文件、图片、粘贴文本)都在后台识别,完成后停在「待审核」。"""
import asyncio
import hashlib
import io
import json
import logging
import math
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app import models
from app.api import deps
from app.core import permissions, storage
from app.core.api_errors import ApiError, ErrorCode
from app.core.file_paths import VIRTUAL_SOURCE, import_source_file, task_source_file
from app.core.locale import get_locale
from app.core.permissions import Permission
from app.crud.crud_question import is_question_visible
from app.crud.crud_subject import subject as crud_subject
from app.models.import_task import ImportMethod, ImportTask, ImportTaskStatus
from app.models.question import Question
from app.services import import_task_service as tasks_svc
from app.services.importing.job import enqueue_import, requeue_import
from app.services.jobs import job_service

router = APIRouter()
logger = logging.getLogger(__name__)

MethodParam = Literal["auto", "ai", "structured"]
ModeParam = Literal["extract", "solve"]

_CANCELLABLE = (
    ImportTaskStatus.PENDING,
    ImportTaskStatus.PROCESSING,
    ImportTaskStatus.PAUSED,
    ImportTaskStatus.REVIEW_READY,
)
_TEXT_TITLE_MAX = 60


# 标题去掉行首的 markdown 标记与【题目】这类标签,只留正文。
_TITLE_PREFIX_RE = re.compile(r"^(?:[#>*\s]+|-\s+|[【\[][^】\]]{1,10}[】\]]\s*[:：]?\s*)+")


def _title_from_text(content: str) -> str:
    for line in content.splitlines():
        title = _TITLE_PREFIX_RE.sub("", line).strip()
        if title:
            return title[:_TEXT_TITLE_MAX]
    return "text"


class ImportTextRequest(BaseModel):
    content: str
    filename: Optional[str] = None
    mode: ModeParam = "extract"
    method: MethodParam = "auto"
    auto_commit: bool = False
    subject_id: Optional[int] = None


class ResumeRequest(BaseModel):
    ids: List[int] = Field(default_factory=list)


async def _resolve_subject(db, user: models.User, subject_id: Optional[int]) -> int:
    """抽取出的图片与题目都归属该学科,创建任务时即确定,不受之后切换学科影响。"""
    subject_id = subject_id if subject_id is not None else user.last_active_subject_id
    if subject_id is None:
        raise ApiError(400, ErrorCode.IMPORT_TASK_SUBJECT_REQUIRED, "请先选择所属学科")
    if await crud_subject.get(db, id=subject_id) is None:
        raise ApiError(404, ErrorCode.UPLOAD_SUBJECT_NOT_FOUND, "Subject not found")
    deps.require(user, Permission.EDIT_QUESTION, subject_id=subject_id)
    return subject_id


def _new_task(
    *,
    user: models.User,
    subject_id: int,
    filename: str,
    file_type: str,
    content: bytes,
    source_sha256: str,
    method: str,
    mode: str,
    auto_commit: bool,
) -> ImportTask:
    return ImportTask(
        user_id=user.id,
        subject_id=subject_id,
        file_path=VIRTUAL_SOURCE,
        source_sha256=source_sha256,
        content_sha256=hashlib.sha256(content).hexdigest(),
        original_filename=filename,
        file_type=file_type,
        status=ImportTaskStatus.PENDING,
        source=tasks_svc.SOURCE_IMPORT,
        description=f"Import {filename}",
        method=ImportMethod.AI.value if file_type == "image" else method,
        mode=mode,
        auto_commit=auto_commit,
        locale=get_locale(),
    )


async def _get_owned_task(db, task_id: int, user: models.User) -> ImportTask:
    task = await db.get(ImportTask, task_id)
    if task is None:
        raise ApiError(404, ErrorCode.IMPORT_TASK_NOT_FOUND, "Task not found")
    if task.user_id != user.id and not user.is_superuser:
        raise ApiError(403, ErrorCode.IMPORT_TASK_FORBIDDEN, "Not enough permissions")
    return task


async def _serialize_one(db, task: ImportTask) -> dict:
    positions = await tasks_svc.queue_positions(db, [task.id])
    return tasks_svc.serialize(task, queue_ahead=positions.get(task.id))


@router.get("/queue-status", response_model=dict)
async def get_queue_status(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """队列各状态的任务数,以及排队/处理中的任务。"""
    stats_result = await db.execute(
        select(ImportTask.status, func.count(ImportTask.id))
        .where(ImportTask.source.in_(tasks_svc.QUEUE_SOURCES))
        .group_by(ImportTask.status)
    )
    stats_dict = {status: count for status, count in stats_result.all()}
    stats = {status.value: stats_dict.get(status, 0) for status in ImportTaskStatus}

    active_stmt = (
        select(ImportTask)
        .options(selectinload(ImportTask.user))
        .where(
            ImportTask.status.in_([ImportTaskStatus.PENDING, ImportTaskStatus.PROCESSING]),
            ImportTask.source.in_(tasks_svc.QUEUE_SOURCES),
        )
        .order_by(ImportTask.created_at.asc(), ImportTask.id.asc())
    )
    if not current_user.is_superuser:
        active_stmt = active_stmt.where(ImportTask.user_id == current_user.id)
    active_tasks = (await db.execute(active_stmt)).scalars().all()
    return {
        "stats": stats,
        "active_tasks": [
            {
                "id": task.id,
                "original_filename": task.original_filename,
                "status": task.status,
                "created_at": task.created_at,
                "owner_name": task.user.full_name if task.user else "Unknown",
                "queue_position": index + 1,
            }
            for index, task in enumerate(active_tasks)
        ],
    }


@router.get("/summary", response_model=dict)
async def get_import_summary(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """当前用户各状态的导入数(侧边栏角标、暂停提示用)。"""
    return await tasks_svc.summary(db, owner_id=current_user.id)


@router.get("", response_model=dict)
async def list_import_tasks(
    *,
    db: deps.SessionDep,
    page: int = 1,
    size: int = Query(20, ge=1, le=200),
    status: Optional[str] = Query(None, description="Comma-separated statuses"),
    user_id: Optional[int] = None,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """导入列表:普通用户只看自己的;管理员可看全部或按用户筛选。"""
    conditions = tasks_svc.visible_condition(
        current_user.id, is_superuser=current_user.is_superuser, owner_id=user_id
    )
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        valid = {s.value for s in ImportTaskStatus}
        conditions.append(ImportTask.status.in_([s for s in wanted if s in valid]))

    total = (
        await db.execute(select(func.count()).select_from(ImportTask).where(*conditions))
    ).scalar_one()
    tasks = (
        await db.execute(
            select(ImportTask)
            .options(selectinload(ImportTask.user))
            .where(*conditions)
            .order_by(ImportTask.created_at.desc(), ImportTask.id.desc())
            .offset((max(page, 1) - 1) * size)
            .limit(size)
        )
    ).scalars().all()
    positions = await tasks_svc.queue_positions(
        db, [t.id for t in tasks if t.status == ImportTaskStatus.PENDING]
    )
    return {
        "items": [tasks_svc.serialize(t, queue_ahead=positions.get(t.id)) for t in tasks],
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size) if size > 0 else 0,
    }


@router.post("", response_model=dict)
async def create_import_tasks(
    *,
    db: deps.SessionDep,
    files: List[UploadFile] = File(...),
    mode: ModeParam = Query("extract", description="extract: keep the document's answers; solve: let AI answer"),
    method: MethodParam = Query("auto", description="auto: tag parsing when the document has 【题目】 tags, else AI"),
    auto_commit: bool = Query(False, description="Save questions right after recognition, skipping review"),
    subject_id: Optional[int] = Query(None),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """每个文件创建一条导入任务(压缩包整体为一条),由 worker 在后台识别。"""
    if not files:
        raise ApiError(400, ErrorCode.IMPORT_TASK_NO_FILES, "No files provided")
    subject_id = await _resolve_subject(db, current_user, subject_id)

    created: List[ImportTask] = []
    skipped: List[str] = []
    for file in files:
        filename = Path(file.filename or "").name or "upload"
        file_type = tasks_svc.file_type_for(filename, file.content_type)
        content = await file.read()
        if file_type is None or not content:
            skipped.append(filename)
            continue
        if file_type == "archive" and not zipfile.is_zipfile(io.BytesIO(content)):
            skipped.append(filename)
            continue
        sha256 = await asyncio.to_thread(storage.put_bytes, content)
        task = _new_task(
            user=current_user,
            subject_id=subject_id,
            filename=filename,
            file_type=file_type,
            content=content,
            source_sha256=sha256,
            method=method,
            mode=mode,
            auto_commit=auto_commit,
        )
        db.add(task)
        created.append(task)

    if not created:
        raise ApiError(
            400,
            ErrorCode.IMPORT_TASK_NO_VALID_FILES,
            "No valid files found (supported: .docx, .md, .zip, images)",
        )
    # 先 flush 拿到任务 id,再为每条任务排一个执行 job,一起提交。
    await db.flush()
    for task in created:
        await enqueue_import(db, task)
    await db.commit()
    for task in created:
        await db.refresh(task)
    positions = await tasks_svc.queue_positions(db, [t.id for t in created])
    return {
        "items": [tasks_svc.serialize(t, queue_ahead=positions.get(t.id)) for t in created],
        "skipped": skipped,
    }


@router.post("/text", response_model=dict)
async def create_text_import_task(
    *,
    db: deps.SessionDep,
    payload: ImportTextRequest,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """粘贴的文本作为一条导入任务;名称默认取第一行。"""
    content = payload.content.strip()
    if not content:
        raise ApiError(400, ErrorCode.IMPORT_TASK_EMPTY_TEXT, "Text is empty")
    subject_id = await _resolve_subject(db, current_user, payload.subject_id)

    title = (payload.filename or "").strip() or _title_from_text(content)
    raw = content.encode("utf-8")
    sha256 = await asyncio.to_thread(storage.put_bytes, raw)
    task = _new_task(
        user=current_user,
        subject_id=subject_id,
        filename=title,
        file_type="text",
        content=raw,
        source_sha256=sha256,
        method=payload.method,
        mode=payload.mode,
        auto_commit=payload.auto_commit,
    )
    db.add(task)
    await db.flush()
    await enqueue_import(db, task)
    await db.commit()
    await db.refresh(task)
    return await _serialize_one(db, task)


@router.post("/resume", response_model=dict)
async def resume_import_tasks(
    *,
    db: deps.SessionDep,
    payload: ResumeRequest,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """把暂停的任务放回队列;不传 ids 时恢复全部(管理员为所有人的,其他人为自己的)。"""
    owner_id = None if current_user.is_superuser else current_user.id
    if payload.ids:
        count = await tasks_svc.resume_ids(db, payload.ids, owner_id=owner_id)
    else:
        count = await tasks_svc.resume_all(db, owner_id=owner_id)
    await db.commit()
    return {"count": count}


@router.post("/reset-stuck", response_model=dict)
async def reset_stuck_tasks(
    *,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """把卡在「处理中」的导入放回队列(管理员为所有人的,其他人为自己的)。"""
    count = await job_service.requeue_running(
        db,
        user_id=None if current_user.is_superuser else current_user.id,
        types=[tasks_svc.JOB_TYPE],
    )
    await db.commit()
    return {"message": f"Reset {count} tasks to pending state", "count": count}


@router.get("/{task_id}", response_model=dict)
async def get_import_task_status(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    task = await _get_owned_task(db, task_id, current_user)
    return await _serialize_one(db, task)


@router.get("/{task_id}/result", response_model=dict)
async def get_import_task_result(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """待审核的识别结果:题目、材料、题组、整卷结构,以及文件级重复提示。"""
    task = await _get_owned_task(db, task_id, current_user)
    payload = await asyncio.to_thread(tasks_svc.load_result, task) if task.status == ImportTaskStatus.REVIEW_READY else None
    if payload is None:
        raise ApiError(404, ErrorCode.IMPORT_TASK_RESULT_UNAVAILABLE, "Recognition result is not available")
    payload["content_sha256"] = task.content_sha256
    payload["duplicate_of"] = await tasks_svc.find_duplicate_of(
        db, task.content_sha256, exclude_task_id=task.id
    )
    payload["task"] = await _serialize_one(db, task)
    return payload


@router.post("/{task_id}/cancel", response_model=dict)
async def cancel_import_task(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """取消排队/处理中/暂停的任务,或放弃待审核的结果。处理中的任务会在几秒内停下。"""
    task = await _get_owned_task(db, task_id, current_user)
    if task.status not in _CANCELLABLE:
        raise ApiError(400, ErrorCode.IMPORT_TASK_ALREADY_FINISHED, "Task already finished")
    # 排队 / 处理中 / 暂停:取消它的 job,状态经投影同步回导入任务;
    # 待审核(job 已结束)或找不到 job 的旧数据:直接放弃识别结果。
    cancelled = await job_service.cancel_for_targets(
        db, tasks_svc.JOB_TARGET_TYPE, [task.id], type=tasks_svc.JOB_TYPE
    )
    if not cancelled:
        task.status = ImportTaskStatus.CANCELLED
        task.result_sha256 = None
        task.paused_reason = None
        task.progress = None
        task.updated_at = datetime.utcnow()
    await db.commit()
    return {"message": "Task cancelled"}


def _is_empty_completed(task: ImportTask) -> bool:
    if task.status != ImportTaskStatus.COMPLETED or not task.result_summary:
        return False
    try:
        summary = json.loads(task.result_summary)
        return summary.get("count", len(summary.get("created_question_ids") or [])) == 0
    except (ValueError, AttributeError):
        return False


@router.post("/{task_id}/retry", response_model=dict)
async def retry_import_task(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """重新识别失败、已取消、已暂停或结果为空的任务。"""
    task = await _get_owned_task(db, task_id, current_user)
    retryable = task.status in (
        ImportTaskStatus.FAILED,
        ImportTaskStatus.CANCELLED,
        ImportTaskStatus.PAUSED,
    ) or _is_empty_completed(task)
    if not retryable:
        raise ApiError(
            400,
            ErrorCode.IMPORT_TASK_NOT_RETRYABLE,
            "Only failed, cancelled, paused, or empty completed tasks can be retried",
        )
    # 业务结果清空;执行状态(排队、错误、暂停、服务商、进度)由 job 重新排队时投影清空。
    task.result_summary = None
    task.result_sha256 = None
    # 重新排到队尾。
    task.created_at = datetime.utcnow()
    task.updated_at = datetime.utcnow()
    await db.flush()
    await requeue_import(db, task)
    await db.commit()
    return {"message": "Task queued for retry"}


@router.delete("/{task_id}", response_model=dict)
async def delete_import_task(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """删除导入记录;正在处理的任务会随之停止。"""
    task = await _get_owned_task(db, task_id, current_user)
    source = import_source_file(task.file_path)
    if source is not None:
        try:
            source.unlink()
        except OSError as e:
            logger.warning("Error deleting import source %s: %s", source, e)
    # 先删 job:正在处理的任务会因 job 消失而停止。
    await job_service.delete_for_target(db, tasks_svc.JOB_TARGET_TYPE, task.id)
    await db.delete(task)
    await db.commit()
    return {"message": "Task deleted"}


_SOURCE_MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown; charset=utf-8",
    ".zip": "application/zip",
    ".txt": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


async def _can_view_import_source(db, task: ImportTask, user: models.User) -> bool:
    if user.is_superuser or task.user_id == user.id:
        return True
    # 能看到该任务导入的任一道题,即可对照原卷。
    rows = await db.scalars(
        select(Question)
        .where(Question.import_task_id == task.id, Question.deleted_at.is_(None))
        .limit(500)
    )
    return any(
        is_question_visible(question, user)
        and permissions.can(user, Permission.VIEW_QUESTION, subject_id=question.subject_id)
        for question in rows.all()
    )


@router.get("/{task_id}/source")
async def download_import_source(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> FileResponse:
    task = await db.get(ImportTask, task_id)
    if task is None or not await _can_view_import_source(db, task, current_user):
        raise ApiError(404, ErrorCode.IMPORT_TASK_NOT_FOUND, "Task not found")
    source = task_source_file(task.file_path, task.source_sha256)
    if source is None:
        raise ApiError(404, ErrorCode.IMPORT_TASK_SOURCE_UNAVAILABLE, "Source file not available")
    filename = Path(task.original_filename or source.name).name
    return FileResponse(
        source,
        media_type=_SOURCE_MEDIA_TYPES.get(Path(filename).suffix.lower(), "application/octet-stream"),
        filename=filename,
        headers={"X-Content-Type-Options": "nosniff"},
    )
