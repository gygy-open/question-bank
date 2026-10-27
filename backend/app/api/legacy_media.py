"""旧媒体 URL(/static/media/...)的鉴权下发:经迁移映射读对象存储,未迁移的回退旧目录。

必须在 /static 静态挂载之前注册,否则会被 StaticFiles 抢先匿名下发。
"""
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app import models
from app.api import deps
from app.services import media_service
from app.core.api_errors import ApiError, ErrorCode

router = APIRouter()


@router.get("/static/media/{path:path}", include_in_schema=False)
async def read_legacy_media(
    path: str,
    db: deps.SessionDep,
    current_user: models.User = Depends(deps.get_current_active_user_header_or_cookie),
) -> FileResponse:
    # path 已被解码;重新编码后交给统一的规整逻辑,避免二次解码。
    key = f"{media_service.LEGACY_MEDIA_PREFIX}{path}"
    resolved = await media_service.resolve_legacy_images(
        db, [f"{media_service.LEGACY_MEDIA_PREFIX}{quote(path)}"]
    )
    stored = resolved.get(key)
    if stored is None:
        raise ApiError(404, ErrorCode.MEDIA_NOT_FOUND, "Not found")
    return FileResponse(
        stored.path,
        media_type=stored.mime,
        headers={
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
        },
    )
