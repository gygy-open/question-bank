"""MCP 媒体上传:预签名上传地址。

为什么不直接让客户端带 API Key 上传:执行 curl 的是模型,而 Key 写在客户端配置里,
模型拿不到(也不该拿到)。于是由 MCP 工具(请求已带 Key 鉴权)签发一个短时 URL,
模型用它把本地文件直接 POST 上来,文件内容不经过模型上下文。

令牌只是「Key 的短时委托」:每次上传都重新校验 Key 未撤销、用户有效、MCP 开启、
对学科有编辑权限。签名密钥由 SECRET_KEY 派生且与登录 JWT 不同,两者无法互相冒用。
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Request, UploadFile, status
from jose import JWTError, jwt

from app.api import deps
from app.core import permissions
from app.core.api_errors import ApiError, ErrorCode
from app.core.config import settings
from app.core.permissions import Permission
from app.crud.crud_api_key import api_key as crud_api_key
from app.crud.crud_subject import subject as crud_subject
from app.crud.crud_user import user as crud_user
from app.models.media_asset import MediaAsset, MediaKind, MediaPurpose
from app.services import media_service
from app.services.activity_logger import log_activity
from app.services.mcp_settings import is_mcp_enabled

logger = logging.getLogger(__name__)

UPLOAD_TTL = timedelta(minutes=10)
_ALGORITHM = "HS256"
_TOKEN_TYPE = "mcp_upload"

router = APIRouter()


def _signing_key() -> str:
    return hmac.new(settings.SECRET_KEY.encode(), b"qb-mcp-upload", hashlib.sha256).hexdigest()


def create_upload_token(*, user_id: int, key_id: int, subject_id: int, now: Optional[datetime] = None) -> tuple[str, datetime]:
    expires = (now or datetime.now(timezone.utc)) + UPLOAD_TTL
    claims = {"typ": _TOKEN_TYPE, "uid": user_id, "kid": key_id, "sid": subject_id, "exp": expires}
    return jwt.encode(claims, _signing_key(), algorithm=_ALGORITHM), expires


def _decode(token: str) -> Dict[str, Any]:
    try:
        claims = jwt.decode(token, _signing_key(), algorithms=[_ALGORITHM])
    except JWTError:
        claims = {}
    if claims.get("typ") != _TOKEN_TYPE or not all(isinstance(claims.get(k), int) for k in ("uid", "kid", "sid")):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, ErrorCode.AUTH_TOKEN_INVALID, "Upload URL is invalid or expired")
    return claims


def media_node(asset: MediaAsset) -> Dict[str, Any]:
    """可直接嵌入 RichDoc 的节点。"""
    node_type = "audio" if asset.kind == MediaKind.AUDIO.value else "image"
    return {"type": node_type, "attrs": {"src": media_service.content_url(asset.id), "assetId": asset.id}}


def asset_payload(asset: MediaAsset) -> Dict[str, Any]:
    return {
        "asset_id": asset.id,
        "kind": asset.kind,
        "mime": asset.mime,
        "byte_size": asset.byte_size,
        "width": asset.width,
        "height": asset.height,
        "node": media_node(asset),
    }


@router.post("/{token}", status_code=status.HTTP_201_CREATED)
async def upload_via_token(
    token: str,
    request: Request,
    db: deps.SessionDep,
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    claims = _decode(token)
    if not await is_mcp_enabled(db):
        raise ApiError(status.HTTP_403_FORBIDDEN, ErrorCode.AUTH_FORBIDDEN, "MCP service is disabled")
    key = await crud_api_key.get(db, id=claims["kid"])
    if key is None or key.user_id != claims["uid"]:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, ErrorCode.AUTH_TOKEN_INVALID, "Upload URL is invalid or expired")
    user = await crud_user.get_with_memberships(db, id=claims["uid"])
    if user is None or not user.is_active:
        raise ApiError(status.HTTP_403_FORBIDDEN, ErrorCode.AUTH_INACTIVE_USER, "Inactive user")
    subject_id = claims["sid"]
    if await crud_subject.get(db, id=subject_id) is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, ErrorCode.SUBJECT_NOT_FOUND, "Subject not found")
    if not permissions.can(user, Permission.EDIT_QUESTION, subject_id=subject_id):
        raise ApiError(status.HTTP_403_FORBIDDEN, ErrorCode.AUTH_FORBIDDEN, "The user doesn't have enough privileges")

    limit = media_service.MAX_AUDIO_BYTES
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise ApiError(
            413, ErrorCode.MEDIA_FILE_TOO_LARGE,
            f"File too large (limit {limit // (1024 * 1024)} MB)", {"limit_mb": limit // (1024 * 1024)},
        )
    asset = await media_service.ingest(
        db,
        data,
        purpose=MediaPurpose.CONTENT,
        subject_id=subject_id,
        actor_id=user.id,
        filename=file.filename,
        allow_audio=True,
    )
    await log_activity(
        db, user.id, "mcp_call", "mcp_tool",
        details={"tool": "media_upload", "key": key.prefix, "ok": True, "asset_id": asset.id},
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(asset)
    return asset_payload(asset)
