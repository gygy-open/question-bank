from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.orm import selectinload
from app import models, schemas
from app.api import deps
from app.core.config import settings
from app.models.import_task import ImportTask, ImportTaskStatus
import shutil
import uuid
from pathlib import Path
import asyncio
from datetime import datetime
import math
import json

router = APIRouter()

@router.get("/queue-status", response_model=dict)
async def get_queue_status(
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get global queue statistics and active tasks.
    """
    # 1. Get stats
    stats_stmt = select(ImportTask.status, func.count(ImportTask.id)).group_by(ImportTask.status)
    stats_result = await db.execute(stats_stmt)
    stats_dict = {status: count for status, count in stats_result.all()}
    
    # Ensure all statuses are present
    stats = {
        "pending": stats_dict.get(ImportTaskStatus.PENDING, 0),
        "processing": stats_dict.get(ImportTaskStatus.PROCESSING, 0),
        "completed": stats_dict.get(ImportTaskStatus.COMPLETED, 0),
        "failed": stats_dict.get(ImportTaskStatus.FAILED, 0),
        "cancelled": stats_dict.get(ImportTaskStatus.CANCELLED, 0),
    }

    # 2. Get active tasks (Pending & Processing) with User info
    # Ordered by created_at asc (FIFO queue)
    active_stmt = select(ImportTask).options(selectinload(ImportTask.user))\
        .where(ImportTask.status.in_([ImportTaskStatus.PENDING, ImportTaskStatus.PROCESSING]))
    
    # Access Control for active tasks list
    if not current_user.is_superuser:
        active_stmt = active_stmt.where(ImportTask.user_id == current_user.id)

    active_stmt = active_stmt.order_by(ImportTask.created_at.asc())
        
    active_result = await db.execute(active_stmt)
    active_tasks_db = active_result.scalars().all()
    
    active_tasks = []
    for index, task in enumerate(active_tasks_db):
        active_tasks.append({
            "id": task.id,
            "original_filename": task.original_filename,
            "status": task.status,
            "created_at": task.created_at,
            "owner_name": task.user.full_name if task.user else "Unknown",
            "queue_position": index + 1
        })
        
    return {
        "stats": stats,
        "active_tasks": active_tasks
    }

@router.get("", response_model=dict)
async def list_import_tasks(
    *,
    db: deps.SessionDep,
    page: int = 1,
    size: int = 10,
    status: Optional[str] = None,
    user_id: Optional[int] = None,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    List import tasks for all users.
    """
    skip = (page - 1) * size
    
    # Base query conditions
    conditions = [ImportTask.source == "batch_upload"]
    if status:
        conditions.append(ImportTask.status == status)
    
    # Access Control
    if current_user.is_superuser:
        if user_id:
            conditions.append(ImportTask.user_id == user_id)
    else:
        conditions.append(ImportTask.user_id == current_user.id)
    
    # Count query
    count_stmt = select(func.count()).select_from(ImportTask).where(*conditions)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    stmt = select(ImportTask).options(selectinload(ImportTask.user))\
        .where(*conditions)\
        .order_by(ImportTask.created_at.desc())\
        .offset(skip)\
        .limit(size)
    
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    
    return {
        "items": [
            {
                "id": t.id,
                "original_filename": t.original_filename,
                "status": t.status,
                "created_at": t.created_at,
                "error_message": t.error_message,
                "result_summary": t.result_summary,
                "description": t.description,
                "source": t.source,
                "owner_name": t.user.full_name if t.user else "Unknown"
            }
            for t in tasks
        ],
        "total": total,
        "page": page,
        "size": size,
        "pages": math.ceil(total / size) if size > 0 else 0
    }

@router.post("", response_model=List[dict])
async def create_import_tasks(
    *,
    db: deps.SessionDep,
    files: List[UploadFile] = File(...),
    mode: str = Query("extract", description="Processing mode: extract or solve"),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Upload multiple files for processing. Each file becomes an ImportTask.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    created_tasks = []
    
    # Use a unique directory for this upload session
    upload_session_id = str(uuid.uuid4())
    upload_dir = settings.UPLOAD_DIR / upload_session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    for file in files:
        # Determine file type
        ext = Path(file.filename).suffix.lower()
        if ext == '.docx':
            file_type = 'docx'
        elif ext == '.md':
            file_type = 'markdown'
        else:
            continue 
            
        # Save file
        file_path = upload_dir / file.filename
        
        # We need to read and write async or in thread
        content = await file.read()
        await asyncio.to_thread(file_path.write_bytes, content)
        
        # Create task record
        task = ImportTask(
            user_id=current_user.id,
            file_path=str(file_path),
            original_filename=file.filename,
            file_type=file_type,
            status=ImportTaskStatus.PENDING,
            source="batch_upload",
            description=f"Import {file.filename}",
            mode=mode
        )
        db.add(task)
        created_tasks.append(task)
    
    if not created_tasks:
         raise HTTPException(status_code=400, detail="No valid files found (supported: .docx, .md)")

    await db.commit()
    
    # Refresh to get IDs
    for task in created_tasks:
        await db.refresh(task)
        
    return [
        {
            "id": t.id,
            "original_filename": t.original_filename,
            "status": t.status,
            "created_at": t.created_at
        }
        for t in created_tasks
    ]

@router.post("/reset-stuck", response_model=dict)
async def reset_stuck_tasks(
    *,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Reset tasks that are stuck in processing state to pending.
    """
    stmt = select(ImportTask).where(
        ImportTask.status == ImportTaskStatus.PROCESSING,
        ImportTask.source == "batch_upload"
    )
    
    if not current_user.is_superuser:
        stmt = stmt.where(ImportTask.user_id == current_user.id)
        
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    
    count = 0
    for task in tasks:
        task.status = ImportTaskStatus.PENDING
        task.error_message = None
        task.updated_at = datetime.utcnow()
        count += 1
        
    await db.commit()
    
    return {"message": f"Reset {count} tasks to pending state", "count": count}

@router.get("/{task_id}", response_model=dict)
async def get_import_task_status(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get status of an import task.
    """
    stmt = select(ImportTask).where(ImportTask.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    return {
        "id": task.id,
        "original_filename": task.original_filename,
        "status": task.status,
        "error_message": task.error_message,
        "result_summary": task.result_summary,
        "created_at": task.created_at,
        "description": task.description,
        "source": task.source
    }

@router.post("/{task_id}/cancel", response_model=dict)
async def cancel_import_task(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Cancel an import task.
    """
    stmt = select(ImportTask).where(ImportTask.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    if task.status in [ImportTaskStatus.COMPLETED, ImportTaskStatus.FAILED, ImportTaskStatus.CANCELLED]:
        raise HTTPException(status_code=400, detail="Task already finished")
        
    # Update task status
    task.status = ImportTaskStatus.CANCELLED
    await db.commit()
    
    return {"message": "Task cancelled"}

@router.post("/{task_id}/retry", response_model=dict)
async def retry_import_task(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Retry a failed import task.
    """
    stmt = select(ImportTask).where(ImportTask.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    # Check if retry is allowed
    can_retry = False
    if task.status in [ImportTaskStatus.FAILED, ImportTaskStatus.CANCELLED]:
        can_retry = True
    elif task.status == ImportTaskStatus.COMPLETED:
        # Allow retry if 0 questions were extracted
        try:
            if task.result_summary:
                summary = json.loads(task.result_summary)
                if summary.get("count", 0) == 0:
                    can_retry = True
        except Exception:
            pass

    if not can_retry:
        raise HTTPException(status_code=400, detail="Only failed, cancelled, or empty completed tasks can be retried")
        
    # Reset task status
    task.status = ImportTaskStatus.PENDING
    task.error_message = None
    task.result_summary = None
    task.created_at = datetime.utcnow() # Update timestamp to move to top of queue? Or keep original? Maybe update created_at so it looks new.
    
    await db.commit()
    
    return {"message": "Task queued for retry"}

@router.delete("/{task_id}", response_model=dict)
async def delete_import_task(
    *,
    db: deps.SessionDep,
    task_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Delete an import task.
    """
    stmt = select(ImportTask).where(ImportTask.id == task_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.user_id != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Not enough permissions")
        
    # Delete file if exists
    try:
        file_path = Path(task.file_path)
        if file_path.exists() and file_path.is_file():
            file_path.unlink()
    except Exception as e:
        print(f"Error deleting file: {e}")
        
    await db.delete(task)
    await db.commit()
    
    return {"message": "Task deleted"}
