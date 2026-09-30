from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app import models
from app.api import deps
from app.core import storage
from app.core.permissions import Permission
from app.crud.crud_subject import subject as crud_subject
from app.models.media_asset import MediaPurpose
from app.schemas.media import MediaAssetPage, MediaAssetRead, MediaReferences
from app.services import media_library, media_service

router = APIRouter()
subject_router = APIRouter()


async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read(media_service.MAX_IMAGE_BYTES + 1)
    if len(data) > media_service.MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="文件过大（上限 10 MB）")
    return data


@subject_router.post(
    "/{subject_id}/media", response_model=MediaAssetRead, status_code=status.HTTP_201_CREATED
)
async def upload_subject_media(
    subject_id: int,
    db: deps.SessionDep,
    file: UploadFile = File(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    if await crud_subject.get(db, id=subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found")
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    asset = await media_service.ingest(
        db,
        await _read_upload(file),
        purpose=MediaPurpose.CONTENT,
        subject_id=subject_id,
        actor_id=current_user.id,
        filename=file.filename,
    )
    await db.commit()
    return asset


@subject_router.get("/{subject_id}/media", response_model=MediaAssetPage)
async def list_subject_media(
    subject_id: int,
    db: deps.SessionDep,
    kind: Optional[Literal["image", "audio"]] = None,
    used: Optional[bool] = None,
    q: Optional[str] = Query(None, max_length=100),
    uploader_id: Optional[int] = None,
    sort: media_library.MediaSort = "newest",
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=100),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    return await media_library.list_subject_media(
        db, subject_id, kind=kind, used=used, q=q, uploader_id=uploader_id,
        sort=sort, page=page, size=size,
    )


@router.post("/me", response_model=MediaAssetRead, status_code=status.HTTP_201_CREATED)
async def upload_personal_media(
    db: deps.SessionDep,
    purpose: Literal["avatar", "chat"] = Query(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    asset = await media_service.ingest(
        db,
        await _read_upload(file),
        purpose=MediaPurpose(purpose),
        actor_id=current_user.id,
        filename=file.filename,
    )
    await db.commit()
    return asset


@router.get("/{asset_id}", response_model=MediaAssetRead)
async def read_media(
    asset_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user_header_or_cookie),
) -> Any:
    return await media_service.get_readable(db, asset_id, current_user)


@router.get("/{asset_id}/references", response_model=MediaReferences)
async def read_media_references(
    asset_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    await media_service.get_readable(db, asset_id, current_user)
    return await media_library.describe_references(db, asset_id, current_user)


@router.get("/{asset_id}/content")
async def read_media_content(
    asset_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user_header_or_cookie),
) -> FileResponse:
    asset = await media_service.get_readable(db, asset_id, current_user)
    path = storage.object_path(asset.sha256)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Media file missing")
    filename = asset.original_filename or f"media-{asset.id}{media_service.extension_for(asset.mime)}"
    return FileResponse(
        path,
        media_type=asset.mime,
        filename=filename,
        content_disposition_type="inline",
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
