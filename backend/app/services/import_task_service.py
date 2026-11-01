"""导入任务:创建、源文件摄取、待审核结果存取、按服务商暂停与恢复、对外序列化。

所有导入都以 ImportTask 的形式由 worker 在后台执行;抽取完成后停在 REVIEW_READY,
用户审核后经整卷导入提交入库(`auto_commit` 的任务则由 worker 直接入库)。
API 与 worker 共用本模块。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import ColumnElement, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.file_paths import task_source_file
from app.models.composition import Composition
from app.models.import_task import (
    ImportMethod,
    ImportPauseReason,
    ImportTask,
    ImportTaskStatus,
)

logger = logging.getLogger(__name__)

SOURCE_IMPORT = "import"
# 列表、worker 认可的来源;batch_upload 为旧版批量导入。
QUEUE_SOURCES = (SOURCE_IMPORT, "batch_upload")
# 服务不可达而暂停的任务,隔这么久自动放回队列试探一次。
UNAVAILABLE_RETRY_AFTER = timedelta(minutes=5)

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
_FILE_TYPES = {
    ".docx": "docx",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "markdown",
    ".zip": "archive",
}

# 失败原因码(前端据此翻译);原始错误文本另存 error_message。
ERROR_NO_QUESTIONS = "no_questions"
ERROR_SOURCE_UNAVAILABLE = "source_unavailable"
ERROR_PARSE_FAILED = "parse_failed"
ERROR_AI_DOCUMENT = "ai_document"
ERROR_AI_UNKNOWN = "ai_unknown"


class SourceUnavailable(Exception):
    """任务源文件已不在存储里。"""


def file_type_for(filename: str, content_type: Optional[str] = None) -> Optional[str]:
    suffix = Path(filename or "").suffix.lower()
    if suffix in _FILE_TYPES:
        return _FILE_TYPES[suffix]
    if suffix in _IMAGE_SUFFIXES or (content_type or "").startswith("image/"):
        return "image"
    return None


def method_of(task: ImportTask) -> str:
    if task.file_type == "image":
        return ImportMethod.AI.value
    return task.method or ImportMethod.AI.value


def needs_ai(task: ImportTask) -> Optional[bool]:
    """是否需要 AI;「自动」在摄取前无法确定,返回 None。"""
    method = method_of(task)
    if method == ImportMethod.STRUCTURED.value:
        return False
    if method == ImportMethod.AUTO.value:
        return None
    return True


def purpose_of(task: ImportTask) -> str:
    return "vision" if task.file_type == "image" else "text"


def progress_of(task: ImportTask) -> Dict[str, Any]:
    if not task.progress:
        return {}
    try:
        value = json.loads(task.progress)
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def dump_progress(**values: Any) -> str:
    return json.dumps({k: v for k, v in values.items() if v is not None}, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# 待审核结果
# --------------------------------------------------------------------------- #
def save_result(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    return storage.put_bytes(raw)


def load_result(task: ImportTask) -> Optional[Dict[str, Any]]:
    if not task.result_sha256 or not storage.exists(task.result_sha256):
        return None
    try:
        payload = json.loads(storage.read_bytes(task.result_sha256))
    except (ValueError, storage.StorageError) as exc:
        logger.warning("Unreadable import result for task %s: %s", task.id, exc)
        return None
    return payload if isinstance(payload, dict) else None


async def find_duplicate_of(
    db: AsyncSession, content_sha256: Optional[str], *, exclude_task_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """此前已成功导入过内容完全相同的文件时返回其信息;只提示,不阻塞。"""
    if not content_sha256:
        return None
    stmt = (
        select(ImportTask)
        .where(
            ImportTask.content_sha256 == content_sha256,
            ImportTask.status == ImportTaskStatus.COMPLETED,
        )
        .order_by(ImportTask.created_at.desc())
    )
    if exclude_task_id is not None:
        stmt = stmt.where(ImportTask.id != exclude_task_id)
    task = (await db.execute(stmt)).scalars().first()
    if task is None:
        return None
    comp = (
        await db.execute(select(Composition).where(Composition.source_import_task_id == task.id))
    ).scalars().first()
    return {
        "import_task_id": task.id,
        "original_filename": task.original_filename,
        "imported_at": task.created_at.isoformat() if task.created_at else None,
        "composition_id": comp.id if comp else None,
        "composition_scope": comp.scope_type.value if comp and comp.scope_type else None,
    }


# --------------------------------------------------------------------------- #
# 摄取
# --------------------------------------------------------------------------- #
@dataclass
class IngestedSource:
    markdown: str = ""
    image_data: Optional[bytes] = None
    filename: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


async def ingest_task_source(db: AsyncSession, task: ImportTask) -> IngestedSource:
    """读取任务源文件并转成 markdown(图片任务则为图像字节),文档内图片入库为学科资产。"""
    from app.services.importing.ingest import (
        DocxIngestor,
        MarkdownArchiveIngestor,
        MarkdownIngestor,
        decode_markdown_bytes,
    )
    from app.services.importing.media import ImportImageSink

    source = task_source_file(task.file_path, task.source_sha256)
    if source is None:
        raise SourceUnavailable("Source file is no longer available")

    filename = task.original_filename
    sink = ImportImageSink(db, subject_id=task.subject_id, actor_id=task.user_id)
    if task.file_type == "image":
        data = await asyncio.to_thread(source.read_bytes)
        return IngestedSource(image_data=data, filename=filename)
    if task.file_type == "docx":
        doc = await DocxIngestor().ingest(source, store=sink.store, filename=filename)
    elif task.file_type == "archive":
        doc = await MarkdownArchiveIngestor().ingest(source, store=sink.store, filename=filename)
    elif task.file_type in ("markdown", "text"):
        raw = await asyncio.to_thread(source.read_bytes)
        text, _encoding = decode_markdown_bytes(raw, filename)
        doc = await MarkdownIngestor().ingest(text, filename=filename)
    else:
        raise ValueError(f"Unsupported file type: {task.file_type}")
    return IngestedSource(markdown=doc.markdown, filename=doc.filename, warnings=list(doc.warnings))


def review_payload(
    task: ImportTask, source: IngestedSource, extraction: Any, *, method: str
) -> Dict[str, Any]:
    """与旧同步上传接口相同的审核数据形态,前端审核界面直接使用。"""
    from app.services.importing.review import extracted_stimuli_to_review, extracted_to_v2_review

    return {
        "questions": extracted_to_v2_review(list(extraction.questions or []), subject_id=task.subject_id),
        "stimuli": extracted_stimuli_to_review(list(extraction.stimuli or [])),
        "question_groups": list(extraction.question_groups or []),
        "paper": extraction.paper,
        "warnings": source.warnings,
        "method": method,
    }


# --------------------------------------------------------------------------- #
# 暂停与恢复
# --------------------------------------------------------------------------- #
async def _sibling_ids_for_provider(
    db: AsyncSession, provider_id: Optional[int], *, exclude_id: Optional[int] = None
) -> List[int]:
    """排队中、需要(或可能需要)AI、且默认模型落在同一服务商上的任务。"""
    from app.services.ai_resolver import resolve_provider_id

    stmt = select(ImportTask).where(
        ImportTask.status == ImportTaskStatus.PENDING,
        ImportTask.source.in_(QUEUE_SOURCES),
    )
    if exclude_id is not None:
        stmt = stmt.where(ImportTask.id != exclude_id)
    ids: List[int] = []
    cache: Dict[tuple, Optional[int]] = {}
    for task in (await db.execute(stmt)).scalars().all():
        if needs_ai(task) is False:
            continue
        key = (task.user_id, purpose_of(task))
        if key not in cache:
            cache[key] = await resolve_provider_id(db, user_id=task.user_id, purpose=purpose_of(task))  # type: ignore[arg-type]
        if cache[key] == provider_id:
            ids.append(task.id)
    return ids


async def pause_for_provider(
    db: AsyncSession,
    *,
    task_id: int,
    reason: ImportPauseReason,
    provider_id: Optional[int],
    message: Optional[str] = None,
) -> int:
    """暂停当前任务和同一服务商下排队中的 AI 任务,返回被暂停的数量。调用方负责 commit。"""
    now = datetime.utcnow()
    values = dict(
        status=ImportTaskStatus.PAUSED,
        paused_reason=reason.value,
        provider_id=provider_id,
        error_message=message,
        updated_at=now,
    )
    current = await db.execute(
        update(ImportTask)
        .where(ImportTask.id == task_id, ImportTask.status == ImportTaskStatus.PROCESSING)
        .values(**values, progress=None)
        .execution_options(synchronize_session=False)
    )
    sibling_ids = await _sibling_ids_for_provider(db, provider_id, exclude_id=task_id)
    paused = current.rowcount or 0
    if sibling_ids:
        result = await db.execute(
            update(ImportTask)
            .where(ImportTask.id.in_(sibling_ids), ImportTask.status == ImportTaskStatus.PENDING)
            .values({**values, "error_message": None})
            .execution_options(synchronize_session=False)
        )
        paused += result.rowcount or 0
    return paused


async def _resume_where(db: AsyncSession, *conditions: ColumnElement[bool]) -> int:
    result = await db.execute(
        update(ImportTask)
        .where(ImportTask.status == ImportTaskStatus.PAUSED, *conditions)
        .values(
            status=ImportTaskStatus.PENDING,
            paused_reason=None,
            error_message=None,
            progress=None,
            updated_at=datetime.utcnow(),
        )
        .execution_options(synchronize_session=False)
    )
    return result.rowcount or 0


async def resume_ids(db: AsyncSession, ids: Sequence[int], *, owner_id: Optional[int] = None) -> int:
    if not ids:
        return 0
    conditions = [ImportTask.id.in_(list(ids))]
    if owner_id is not None:
        conditions.append(ImportTask.user_id == owner_id)
    return await _resume_where(db, *conditions)


async def resume_all(db: AsyncSession, *, owner_id: Optional[int] = None) -> int:
    conditions = [ImportTask.source.in_(QUEUE_SOURCES)]
    if owner_id is not None:
        conditions.append(ImportTask.user_id == owner_id)
    return await _resume_where(db, *conditions)


async def resume_provider(db: AsyncSession, provider_id: Optional[int]) -> int:
    """服务商又能成功调用了:恢复因它暂停的全部任务。"""
    if provider_id is None:
        return 0
    return await _resume_where(db, ImportTask.provider_id == provider_id)


async def resume_after_ai_config_change(db: AsyncSession) -> int:
    """AI 设置改动后,把因 Key/模型问题暂停的任务放回队列;仍不可用会再次暂停。调用方负责 commit。"""
    return await _resume_where(
        db,
        ImportTask.paused_reason.in_([ImportPauseReason.AUTH.value, ImportPauseReason.MODEL.value]),
    )


async def resume_stale_unavailable(db: AsyncSession, *, now: Optional[datetime] = None) -> int:
    cutoff = (now or datetime.utcnow()) - UNAVAILABLE_RETRY_AFTER
    return await _resume_where(
        db,
        ImportTask.paused_reason == ImportPauseReason.UNAVAILABLE.value,
        ImportTask.updated_at < cutoff,
    )


# --------------------------------------------------------------------------- #
# 查询与序列化
# --------------------------------------------------------------------------- #
async def summary(db: AsyncSession, *, owner_id: int) -> Dict[str, Any]:
    rows = await db.execute(
        select(ImportTask.status, ImportTask.paused_reason, func.count(ImportTask.id))
        .where(ImportTask.user_id == owner_id, ImportTask.source.in_(QUEUE_SOURCES))
        .group_by(ImportTask.status, ImportTask.paused_reason)
    )
    counts: Dict[str, int] = {status.value: 0 for status in ImportTaskStatus}
    paused: Dict[str, int] = {}
    for status, reason, count in rows.all():
        key = status.value if isinstance(status, ImportTaskStatus) else str(status)
        counts[key] = counts.get(key, 0) + count
        if key == ImportTaskStatus.PAUSED.value and reason:
            paused[reason] = paused.get(reason, 0) + count
    return {"counts": counts, "paused_reasons": paused}


async def queue_positions(db: AsyncSession, task_ids: Iterable[int]) -> Dict[int, int]:
    """排队中的任务前面还有几个任务(含正在处理的);worker 串行执行。"""
    wanted = set(task_ids)
    if not wanted:
        return {}
    active = await db.execute(
        select(ImportTask.id, ImportTask.status)
        .where(
            ImportTask.status.in_([ImportTaskStatus.PENDING, ImportTaskStatus.PROCESSING]),
            ImportTask.source.in_(QUEUE_SOURCES),
        )
        .order_by(ImportTask.created_at, ImportTask.id)
    )
    positions: Dict[int, int] = {}
    ahead = 0
    for task_id, status in active.all():
        if status == ImportTaskStatus.PENDING and task_id in wanted:
            positions[task_id] = ahead
        ahead += 1
    return positions


def serialize(task: ImportTask, *, queue_ahead: Optional[int] = None) -> Dict[str, Any]:
    return {
        "id": task.id,
        "original_filename": task.original_filename,
        "description": task.description,
        "source": task.source,
        "file_type": task.file_type,
        "status": task.status.value if isinstance(task.status, ImportTaskStatus) else task.status,
        "method": task.method,
        "mode": task.mode,
        "auto_commit": bool(task.auto_commit),
        "subject_id": task.subject_id,
        "progress": progress_of(task),
        "paused_reason": task.paused_reason,
        "error_message": task.error_message,
        "result_summary": task.result_summary,
        "has_result": bool(task.result_sha256),
        "queue_ahead": queue_ahead,
        "owner_id": task.user_id,
        "owner_name": (task.user.full_name or task.user.username) if task.__dict__.get("user") else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def visible_condition(user_id: int, *, is_superuser: bool, owner_id: Optional[int] = None) -> List[ColumnElement[bool]]:
    conditions: List[ColumnElement[bool]] = [ImportTask.source.in_(QUEUE_SOURCES)]
    if is_superuser:
        if owner_id is not None:
            conditions.append(ImportTask.user_id == owner_id)
    else:
        conditions.append(ImportTask.user_id == user_id)
    return conditions
