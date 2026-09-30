import asyncio
import hashlib
import logging
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app import models
from app.api import deps
from app.capabilities.errors import DomainError
from app.core import storage
from app.core.permissions import Permission
from app.crud.crud_subject import subject as crud_subject
from app.models.composition import Composition
from app.models.import_task import ImportTask
from app.services.doc_processor import doc_processor
from app.services.importing.media import sign_source_ref
from app.services.importing.review import extracted_stimuli_to_review, extracted_to_v2_review

router = APIRouter()
logger = logging.getLogger(__name__)


async def _check_import_subject(db, user: models.User, subject_id: Optional[int]) -> None:
    """文档内图片会入库为该学科的资产,因此需要该学科的编辑权限。"""
    if subject_id is None:
        return
    if await crud_subject.get(db, id=subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    deps.require(user, Permission.EDIT_QUESTION, subject_id=subject_id)


async def _store_source(content: bytes) -> str:
    return await asyncio.to_thread(storage.put_bytes, content)


def _attach_source_ref(result: dict, sha256: str, user: models.User) -> None:
    """源文件已存入对象存储;前端提交时回传该凭据,服务端验签后关联到导入任务。"""
    result["source_ref"] = sign_source_ref(sha256, user.id)


def _as_review(result: dict, subject_id: int | None) -> dict:
    """把抽取产物就地转成可编辑的 v2 草稿（同步复核路径）。"""
    result["questions"] = extracted_to_v2_review(result.get("questions", []), subject_id=subject_id)
    result["stimuli"] = extracted_stimuli_to_review(result.get("stimuli", []))
    return result


async def _attach_duplicate_hint(result: dict, db, content: bytes) -> dict:
    """标记“与历史导入文件内容完全一致”。只提示，不阻塞；近似重复不在本期承诺范围。"""
    digest = hashlib.sha256(content).hexdigest()
    result["content_sha256"] = digest

    task = (
        await db.execute(
            select(ImportTask)
            .where(ImportTask.content_sha256 == digest)
            .order_by(ImportTask.created_at.desc())
        )
    ).scalars().first()
    if task is None:
        result["duplicate_of"] = None
        return result

    comp = (
        await db.execute(
            select(Composition).where(Composition.source_import_task_id == task.id)
        )
    ).scalars().first()
    result["duplicate_of"] = {
        "import_task_id": task.id,
        "original_filename": task.original_filename,
        "imported_at": task.created_at.isoformat() if task.created_at else None,
        "composition_id": comp.id if comp else None,
    }
    return result

class MarkdownContentRequest(BaseModel):
    content: str
    filename: str = None
    mode: str = "extract"
    method: str = "ai"
    subject_id: int = None

@router.post("/docx")
async def upload_docx(
    db: deps.SessionDep,
    file: UploadFile = File(...),
    mode: str = "extract",
    method: str = "ai",
    subject_id: int = None,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Upload and process a DOCX file."""
    if not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")
    await _check_import_subject(db, current_user, subject_id)

    content = await file.read()
    sha256 = await _store_source(content)

    try:
        result = await doc_processor.process_docx(
            storage.object_path(sha256),
            db=db,
            mode=mode,
            method=method,
            subject_id=subject_id,
            actor_id=current_user.id,
            filename=file.filename,
        )
        _as_review(result, subject_id)
        _attach_source_ref(result, sha256, current_user)
        await _attach_duplicate_hint(result, db, content)
        await db.commit()
        return result
    except DomainError:
        raise
    except Exception as e:
        logger.exception(
            "Failed to process DOCX: filename=%s mode=%s method=%s subject_id=%s",
            file.filename,
            mode,
            method,
            subject_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/markdown")
async def upload_markdown(
    db: deps.SessionDep,
    file: UploadFile = File(None),
    mode: str = "extract",
    method: str = "ai",
    subject_id: int = None,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Process markdown content from file upload."""
    if not file:
        raise HTTPException(status_code=400, detail="File is required")
    
    if not file.filename.endswith('.md'):
        raise HTTPException(status_code=400, detail="Only .md files are supported")
    await _check_import_subject(db, current_user, subject_id)

    markdown_content_bytes = await file.read()
    sha256 = await _store_source(markdown_content_bytes)
    markdown_content = markdown_content_bytes.decode('utf-8')
    
    try:
        result = await doc_processor.process_markdown(markdown_content, db=db, filename=file.filename, mode=mode, method=method, subject_id=subject_id)
        _as_review(result, subject_id)
        _attach_source_ref(result, sha256, current_user)
        await _attach_duplicate_hint(result, db, markdown_content_bytes)
        return result
    except Exception as e:
        logger.exception(
            "Failed to process Markdown: filename=%s mode=%s method=%s subject_id=%s",
            file.filename,
            mode,
            method,
            subject_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/markdown-text")
async def upload_markdown_text(
    db: deps.SessionDep,
    request: MarkdownContentRequest
):
    """Process markdown content from text input."""
    try:
        result = await doc_processor.process_markdown(request.content, db=db, filename=request.filename, mode=request.mode, method=request.method, subject_id=request.subject_id)
        _as_review(result, request.subject_id)
        return result
    except Exception as e:
        logger.exception(
            "Failed to process Markdown text: filename=%s mode=%s method=%s subject_id=%s",
            request.filename,
            request.mode,
            request.method,
            request.subject_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/markdown-archive")
async def upload_markdown_archive(
    db: deps.SessionDep,
    file: UploadFile = File(...),
    mode: str = "extract",
    method: str = "ai",
    subject_id: int = None,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """Process a zip archive containing markdown file(s) plus their local images."""
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip archives are supported")
    await _check_import_subject(db, current_user, subject_id)

    content = await file.read()
    sha256 = await _store_source(content)

    try:
        result = await doc_processor.process_markdown_archive(
            storage.object_path(sha256),
            db=db,
            mode=mode,
            method=method,
            subject_id=subject_id,
            actor_id=current_user.id,
            filename=file.filename,
        )
        _as_review(result, subject_id)
        _attach_source_ref(result, sha256, current_user)
        await db.commit()
        return result
    except DomainError:
        raise
    except (ValueError, zipfile.BadZipFile) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.exception(
            "Failed to process Markdown archive: filename=%s mode=%s method=%s subject_id=%s",
            file.filename,
            mode,
            method,
            subject_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/image-recognition")
async def upload_image_recognition(
    db: deps.SessionDep,
    file: UploadFile = File(...),
    mode: str = "extract",
    subject_id: int = None,
):
    """Upload and process an image file to extract questions using AI vision."""
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are supported")
    
    try:
        result = await doc_processor.process_image(file.file, db=db, mode=mode, subject_id=subject_id)
        _as_review(result, subject_id)
        return result
    except Exception as e:
        logger.exception(
            "Failed to process image: filename=%s mode=%s subject_id=%s",
            file.filename,
            mode,
            subject_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e
