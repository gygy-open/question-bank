import asyncio
import logging
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api import deps
from app.core.config import settings
from app.services.doc_processor import doc_processor

router = APIRouter()
logger = logging.getLogger(__name__)

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
        result["file_path"] = str(file_path)
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
        result["file_path"] = str(file_path)
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
        return result
    except Exception as e:
        logger.exception(
            "Failed to process image: filename=%s mode=%s subject_id=%s",
            file.filename,
            mode,
            subject_id,
        )
        raise HTTPException(status_code=500, detail=str(e)) from e

@router.post("/image")
async def upload_image(file: UploadFile = File(...)):
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Only image files are supported")
    
    # Create images directory if it doesn't exist
    images_dir = settings.MEDIA_DIR / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    ext = Path(file.filename).suffix
    filename = f"{uuid.uuid4()}{ext}"
    file_path = images_dir / filename
    
    # Save file
    def save_image_file():
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
    await asyncio.to_thread(save_image_file)
        
    return {"url": f"/static/media/images/{filename}"}
