from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse

from app import models
from app.api import deps
from app.core import storage
from app.core.permissions import Permission
from app.crud.crud_subject import subject as crud_subject
from app.models.media_asset import MediaPurpose
from app.schemas.media import MediaAssetRead
from app.services import media_service

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
