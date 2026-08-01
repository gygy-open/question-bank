from typing import Any, List, Optional
import asyncio
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError
from app import crud, schemas, models
from app.api import deps
from app.core.vector_store import VectorStore
from app.services import kp_import_service

router = APIRouter()

MAX_IMPORT_SIZE = 5 * 1024 * 1024  # 5 MB


@router.get("", response_model=List[schemas.KnowledgePoint])
async def read_knowledge_points(
    db: deps.SessionDep,
    skip: int = 0,
    limit: int = 100,
    subject_id: Optional[int] = None,
) -> Any:
    """
    Retrieve knowledge points.
    Set limit to -1 to retrieve all knowledge points.
    """
    if limit == -1:
        limit = None
        
    if subject_id:
        knowledge_points = await crud.knowledge_point.get_by_subject(db, subject_id=subject_id, skip=skip, limit=limit)
    else:
        knowledge_points = await crud.knowledge_point.get_multi(db, skip=skip, limit=limit)
    return knowledge_points


# --- Vector sync (deferred indexing) ---

@router.get("/vector-status", response_model=schemas.VectorStatus)
async def get_vector_status(
    db: deps.SessionDep,
    subject_id: Optional[int] = None,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Report whether the knowledge point vectors are in sync with the database.
    Used by the UI to prompt for a manual reindex when needed.
    """
    embedding_configured = VectorStore.is_available()

    if subject_id:
        kps = await crud.knowledge_point.get_by_subject(db, subject_id=subject_id, limit=None)
        db_count = len(kps)
    else:
        all_kps = await crud.knowledge_point.get_multi(db, limit=None)
        db_count = len(all_kps)

    vector_count = VectorStore.count() if embedding_configured else 0

    if not embedding_configured:
        needs_reindex = False
        reason = "未配置向量模型，语义检索不可用"
    elif db_count != vector_count:
        needs_reindex = True
        diff = abs(db_count - vector_count)
        reason = f"{diff} 个知识点尚未同步向量索引"
    else:
        needs_reindex = False
        reason = "向量索引已是最新"

    return schemas.VectorStatus(
        embedding_configured=embedding_configured,
        db_count=db_count,
        vector_count=vector_count,
        needs_reindex=needs_reindex,
        reason=reason,
    )


@router.post("/reindex-vectors", response_model=schemas.ReindexResult)
async def reindex_vectors(
    *,
    db: deps.SessionDep,
    subject_id: Optional[int] = None,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Rebuild the knowledge point vector index from the database.
    """
    if not VectorStore.is_available():
        raise HTTPException(
            status_code=400,
            detail="请先在 AI 供应商与模型中配置并激活 Embedding 模型",
        )
    import time
    started = time.perf_counter()
    try:
        count = await crud.knowledge_point.reindex_vectors(db, subject_id=subject_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return schemas.ReindexResult(
        status="success",
        reindexed=count,
        duration=round(time.perf_counter() - started, 2),
    )


# --- Batch import ---

@router.get("/import-template")
async def download_import_template(
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Download the .xlsx knowledge point import template."""
    content = kp_import_service.generate_template()
    return StreamingResponse(
        iter([content]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="knowledge_points_template.xlsx"'
        },
    )


@router.get("/import-preflight", response_model=schemas.KPImportPreflight)
async def import_preflight(
    *,
    db: deps.SessionDep,
    subject_id: int,
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Impact assessment for the rebuild mode (existing count, affected questions)."""
    result = await kp_import_service.preflight(db, subject_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    return result


@router.post("/import", response_model=schemas.KPImportResult)
async def import_knowledge_points(
    *,
    db: deps.SessionDep,
    file: UploadFile = File(...),
    mode: str = Form("incremental"),
    current_user: models.User = Depends(deps.get_current_active_superuser),
) -> Any:
    """Batch import knowledge points from an .xlsx file."""
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式的文件")
    if mode not in ("incremental", "rebuild"):
        raise HTTPException(status_code=400, detail="无效的导入模式")

    content = await file.read()
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=400, detail="文件过大，请确保文件小于 5MB")

    result = await kp_import_service.import_excel(
        db, file_bytes=content, mode=mode, user_id=current_user.id
    )
    return result


@router.post("", response_model=schemas.KnowledgePoint)
async def create_knowledge_point(
    *,
    db: deps.SessionDep,
    knowledge_point_in: schemas.KnowledgePointCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    try:
        knowledge_point = await crud.knowledge_point.create(db=db, obj_in=knowledge_point_in, user_id=current_user.id)
        return knowledge_point
    except IntegrityError:
        raise HTTPException(status_code=400, detail="Knowledge point with this slug already exists in this subject")

@router.put("/{id}", response_model=schemas.KnowledgePoint)
async def update_knowledge_point(
    *,
    db: deps.SessionDep,
    id: int,
    knowledge_point_in: schemas.KnowledgePointUpdate,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    knowledge_point = await crud.knowledge_point.get(db=db, id=id)
    if not knowledge_point:
        raise HTTPException(status_code=404, detail="Knowledge point not found")
    knowledge_point = await crud.knowledge_point.update(db=db, db_obj=knowledge_point, obj_in=knowledge_point_in, user_id=current_user.id)
    return knowledge_point

@router.get("/{id}", response_model=schemas.KnowledgePoint)
async def read_knowledge_point(
    *,
    db: deps.SessionDep,
    id: int,
) -> Any:
    """
    Get knowledge point by ID.
    """
    knowledge_point = await crud.knowledge_point.get(db=db, id=id)
    if not knowledge_point:
        raise HTTPException(status_code=404, detail="Knowledge point not found")
    return knowledge_point

@router.delete("/{id}", response_model=schemas.KnowledgePoint)
async def delete_knowledge_point(
    *,
    db: deps.SessionDep,
    id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Delete a knowledge point.
    """
    knowledge_point = await crud.knowledge_point.get(db=db, id=id)
    if not knowledge_point:
        raise HTTPException(status_code=404, detail="Knowledge point not found")
    knowledge_point = await crud.knowledge_point.remove(db=db, id=id, user_id=current_user.id)
    return knowledge_point
