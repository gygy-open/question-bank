from typing import Any, Iterator, List, Literal, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse

from app import models
from app.api import deps
from app.core import storage
from app.core.permissions import Permission
from app.crud.crud_subject import subject as crud_subject
from app.models.media_asset import MediaPurpose
from app.schemas.media import (
    MediaAssetPage,
    MediaAssetRead,
    MediaAssetUpdate,
    MediaBatchIds,
    MediaBatchResult,
    MediaBatchSourceUpdate,
    MediaCopyRequest,
    MediaReferences,
    MediaReplaceRequest,
    MediaReplaceResult,
)
from app.services import media_library, media_replace, media_service
from app.core.api_errors import ApiError, ErrorCode

router = APIRouter()
subject_router = APIRouter()


async def _read_upload(file: UploadFile, limit: int = media_service.MAX_IMAGE_BYTES) -> bytes:
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise ApiError(
            413,
            ErrorCode.MEDIA_FILE_TOO_LARGE,
            f"文件过大（上限 {limit // (1024 * 1024)} MB）",
            {"limit_mb": limit // (1024 * 1024)},
        )
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
        raise ApiError(404, ErrorCode.SUBJECT_NOT_FOUND, "Subject not found")
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    asset = await media_service.ingest(
        db,
        await _read_upload(file, media_service.MAX_AUDIO_BYTES),
        purpose=MediaPurpose.CONTENT,
        subject_id=subject_id,
        actor_id=current_user.id,
        filename=file.filename,
        allow_audio=True,
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


@subject_router.post("/{subject_id}/media/batch-delete", response_model=MediaBatchResult)
async def batch_delete_subject_media(
    subject_id: int,
    payload: MediaBatchIds,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    return await media_library.batch_delete(db, subject_id, payload.ids)


@subject_router.post("/{subject_id}/media/batch-update", response_model=MediaBatchResult)
async def batch_update_subject_media(
    subject_id: int,
    payload: MediaBatchSourceUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    deps.require(current_user, Permission.EDIT_QUESTION, subject_id=subject_id)
    return await media_library.batch_update_source(db, subject_id, payload.ids, payload.source)


@subject_router.get("/{subject_id}/media/archive")
async def download_subject_media_archive(
    subject_id: int,
    db: deps.SessionDep,
    ids: List[int] = Query(..., min_length=1, max_length=100),
    current_user: models.User = Depends(deps.get_current_active_user_header_or_cookie),
) -> StreamingResponse:
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    spool = await media_library.archive_assets(db, subject_id, ids)

    def chunks() -> Iterator[bytes]:
        with spool:
            while chunk := spool.read(1024 * 1024):
                yield chunk

    return StreamingResponse(
        chunks(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="media-{subject_id}.zip"',
            "X-Content-Type-Options": "nosniff",
        },
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


@router.patch("/{asset_id}", response_model=MediaAssetRead)
async def update_media(
    asset_id: int,
    payload: MediaAssetUpdate,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await media_library.update_asset(db, asset_id, current_user, payload)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_media(
    asset_id: int,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> None:
    await media_library.delete_asset(db, asset_id, current_user)


@router.post("/{asset_id}/replace", response_model=MediaReplaceResult)
async def replace_media(
    asset_id: int,
    payload: MediaReplaceRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    return await media_replace.replace_asset(db, asset_id, current_user, payload)


@router.post("/{asset_id}/copy", response_model=MediaAssetRead, status_code=status.HTTP_201_CREATED)
async def copy_media_to_subject(
    asset_id: int,
    payload: MediaCopyRequest,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    if await crud_subject.get(db, id=payload.subject_id) is None:
        raise ApiError(404, ErrorCode.SUBJECT_NOT_FOUND, "Subject not found")
    return await media_library.copy_to_subject(db, asset_id, payload.subject_id, current_user)


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
    download: bool = False,
    current_user: models.User = Depends(deps.get_current_active_user_header_or_cookie),
) -> FileResponse:
    asset = await media_service.get_readable(db, asset_id, current_user)
    path = storage.object_path(asset.sha256)
    if not path.is_file():
        raise ApiError(404, ErrorCode.MEDIA_FILE_MISSING, "Media file missing")
    filename = asset.original_filename or f"media-{asset.id}{media_service.extension_for(asset.mime)}"
    return FileResponse(
        path,
        media_type=asset.mime,
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )
