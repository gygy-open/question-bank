import asyncio
import hashlib
import io
import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy import select

from app.api import deps
from app.core.config import settings
from app.models.composition import Composition
from app.models.import_task import ImportTask
from app.services.doc_processor import doc_processor
from app.services.importing.review import extracted_stimuli_to_review, extracted_to_v2_review

router = APIRouter()
logger = logging.getLogger(__name__)


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
):
    """Upload and process a DOCX file."""
    if not file.filename.endswith('.docx'):
        raise HTTPException(status_code=400, detail="Only .docx files are supported")
    
    # Create upload directory
    upload_session_id = str(uuid.uuid4())
    upload_dir = settings.UPLOAD_DIR / upload_session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / file.filename
    
    # Save file
    content = await file.read()
    await asyncio.to_thread(file_path.write_bytes, content)
    
    try:
        result = await doc_processor.process_docx(file_path, db=db, mode=mode, method=method, subject_id=subject_id)
        _as_review(result, subject_id)
        result["file_path"] = str(file_path)
        await _attach_duplicate_hint(result, db, content)
        return result
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
):
    """Process markdown content from file upload."""
    if not file:
        raise HTTPException(status_code=400, detail="File is required")
    
    if not file.filename.endswith('.md'):
        raise HTTPException(status_code=400, detail="Only .md files are supported")
    
    # Create upload directory
    upload_session_id = str(uuid.uuid4())
    upload_dir = settings.UPLOAD_DIR / upload_session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = upload_dir / file.filename
    
    # Save file
    markdown_content_bytes = await file.read()
    await asyncio.to_thread(file_path.write_bytes, markdown_content_bytes)
    
    markdown_content = markdown_content_bytes.decode('utf-8')
    
    try:
        result = await doc_processor.process_markdown(markdown_content, db=db, filename=file.filename, mode=mode, method=method, subject_id=subject_id)
        _as_review(result, subject_id)
        result["file_path"] = str(file_path)
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
):
    """Process a zip archive containing markdown file(s) plus their local images."""
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Only .zip archives are supported")

    upload_session_id = str(uuid.uuid4())
    upload_dir = settings.UPLOAD_DIR / upload_session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename

    content = await file.read()
    await asyncio.to_thread(file_path.write_bytes, content)

    try:
        result = await doc_processor.process_markdown_archive(file_path, db=db, mode=mode, method=method, subject_id=subject_id)
        _as_review(result, subject_id)
        result["file_path"] = str(file_path)
        return result
    except ValueError as e:
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

_IMAGE_EXTENSION_BY_FORMAT = {"PNG": ".png", "JPEG": ".jpg", "GIF": ".gif", "WEBP": ".webp"}
_MAX_IMAGE_BYTES = 10 * 1024 * 1024


def _detect_image_extension(data: bytes) -> str:
    """按文件内容识别图片格式;只放行浏览器可安全显示的位图,扩展名由识别结果决定。"""
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, GIF or WebP images are supported") from exc
    ext = _IMAGE_EXTENSION_BY_FORMAT.get(fmt or "")
    if ext is None:
        raise HTTPException(status_code=400, detail="Only PNG, JPEG, GIF or WebP images are supported")
    return ext


@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    data = await file.read(_MAX_IMAGE_BYTES + 1)
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large (max 10 MB)")
    ext = _detect_image_extension(data)

    images_dir = settings.MEDIA_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    await asyncio.to_thread((images_dir / filename).write_bytes, data)

    return {"url": f"/static/media/images/{filename}"}
