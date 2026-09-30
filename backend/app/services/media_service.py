"""媒体资产的唯一写入口与读取鉴权。

所有上传、导入、识别产生的媒体都经 ingest 入库:服务端按文件内容识别类型、按 sha256
去重、文件落到内容寻址存储;业务代码只持有资产 id。
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Forbidden, NotFound, Unprocessable
from app.core import permissions, storage
from app.core.config import settings
from app.core.permissions import Permission
from app.models.media_asset import MediaAsset, MediaKind, MediaPurpose, MediaStatus
from app.models.user import User

MAX_IMAGE_BYTES = 10 * 1024 * 1024

WEB_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
_PIL_WEB_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}
# 仅导入来源可入库:浏览器无法显示,保留原件以便日后转换。
_PIL_LEGACY_FORMATS = {"TIFF": "image/tiff", "BMP": "image/bmp"}
_EXTENSION_BY_MIME = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/tiff": ".tif",
    "image/bmp": ".bmp",
    "image/emf": ".emf",
    "image/wmf": ".wmf",
}


@dataclass(frozen=True)
class SniffResult:
    kind: str
    mime: str
    width: Optional[int] = None
    height: Optional[int] = None


def _sniff_metafile(data: bytes) -> Optional[str]:
    if data[:4] == b"\x01\x00\x00\x00" and data[40:44] == b" EMF":
        return "image/emf"
    if data[:4] == b"\xd7\xcd\xc6\x9a":
        return "image/wmf"
    if data[:2] in (b"\x01\x00", b"\x02\x00") and data[2:4] == b"\x09\x00":
        return "image/wmf"
    return None


def sniff(data: bytes, *, allow_legacy_formats: bool = False) -> SniffResult:
    """按文件内容识别媒体类型;不在白名单内一律拒绝。"""
    metafile = _sniff_metafile(data)
    if metafile is not None:
        if not allow_legacy_formats:
            raise Unprocessable("不支持的图片格式，请上传 PNG、JPEG、GIF 或 WebP")
        return SniffResult(kind=MediaKind.IMAGE.value, mime=metafile)
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format or ""
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise Unprocessable("无法识别的文件，请上传 PNG、JPEG、GIF 或 WebP 图片") from exc
    mime = _PIL_WEB_FORMATS.get(fmt)
    if mime is None and allow_legacy_formats:
        mime = _PIL_LEGACY_FORMATS.get(fmt)
    if mime is None:
        raise Unprocessable("不支持的图片格式，请上传 PNG、JPEG、GIF 或 WebP")
    return SniffResult(kind=MediaKind.IMAGE.value, mime=mime, width=width, height=height)


def is_displayable(mime: str) -> bool:
    return mime in WEB_IMAGE_MIMES


def extension_for(mime: str) -> str:
    return _EXTENSION_BY_MIME.get(mime, "")


def content_url(asset_id: int) -> str:
    return f"{settings.API_V1_STR}/media/{asset_id}/content"


def _scope_filter(purpose: MediaPurpose, subject_id: Optional[int], owner_user_id: Optional[int]):
    if purpose == MediaPurpose.CONTENT:
        return MediaAsset.subject_id == subject_id
    return MediaAsset.owner_user_id == owner_user_id


async def ingest(
    db: AsyncSession,
    data: bytes,
    *,
    purpose: MediaPurpose,
    actor_id: Optional[int],
    subject_id: Optional[int] = None,
    filename: Optional[str] = None,
    allow_legacy_formats: bool = False,
    max_bytes: int = MAX_IMAGE_BYTES,
) -> MediaAsset:
    """识别、去重并登记一个资产;只 flush,由调用方决定何时提交。"""
    if purpose == MediaPurpose.CONTENT and subject_id is None:
        raise Unprocessable("题目内容图片必须归属学科")
    if purpose != MediaPurpose.CONTENT and actor_id is None:
        raise Unprocessable("个人媒体必须归属用户")
    if len(data) > max_bytes:
        raise Unprocessable(f"文件过大（上限 {max_bytes // (1024 * 1024)} MB）")
    if not data:
        raise Unprocessable("文件为空")

    info = sniff(data, allow_legacy_formats=allow_legacy_formats)
    sha256 = await asyncio.to_thread(storage.put_bytes, data)

    owner_scope = None if purpose == MediaPurpose.CONTENT else actor_id
    existing = await db.scalar(
        select(MediaAsset)
        .where(
            MediaAsset.purpose == purpose.value,
            MediaAsset.sha256 == sha256,
            _scope_filter(purpose, subject_id, owner_scope),
        )
        .order_by(MediaAsset.id)
        .limit(1)
    )
    if existing is not None:
        if existing.deleted_at is not None:
            existing.deleted_at = None
            await db.flush()
        return existing

    asset = MediaAsset(
        subject_id=subject_id if purpose == MediaPurpose.CONTENT else None,
        owner_user_id=actor_id,
        purpose=purpose.value,
        kind=info.kind,
        sha256=sha256,
        mime=info.mime,
        byte_size=len(data),
        width=info.width,
        height=info.height,
        original_filename=(Path(filename).name[:255] if filename else None),
        status=MediaStatus.READY.value,
    )
    db.add(asset)
    await db.flush()
    return asset


def can_read(asset: MediaAsset, user: User) -> bool:
    if user.is_superuser:
        return True
    if asset.purpose == MediaPurpose.CONTENT.value:
        return permissions.can(user, Permission.VIEW_QUESTION, subject_id=asset.subject_id)
    if asset.purpose == MediaPurpose.AVATAR.value:
        return True
    return asset.owner_user_id == user.id


async def get_readable(db: AsyncSession, asset_id: int, user: User) -> MediaAsset:
    # 资产内容不可变;软删除的资产仍可能被冻结稿件引用,对有权限者照常可读。
    asset = await db.get(MediaAsset, asset_id)
    if asset is None or not can_read(asset, user):
        raise NotFound("Media not found")
    return asset


async def get_owned_chat_asset(db: AsyncSession, asset_id: int, user: User) -> MediaAsset:
    asset = await db.get(MediaAsset, asset_id)
    if asset is None or asset.purpose != MediaPurpose.CHAT.value or asset.owner_user_id != user.id:
        raise Forbidden("Media not accessible")
    return asset


def collect_asset_ids(value: Any) -> set[int]:
    """在任意嵌套的 RichDoc / 快照 JSON 中收集图片节点引用的资产 id。"""
    found: set[int] = set()
    stack: list[Any] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("type") == "image":
                asset_id = (node.get("attrs") or {}).get("assetId")
                if isinstance(asset_id, int) and not isinstance(asset_id, bool) and asset_id > 0:
                    found.add(asset_id)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


@dataclass(frozen=True)
class StoredImage:
    path: Path
    mime: str

    @property
    def extension(self) -> str:
        return extension_for(self.mime)


async def load_content_images(
    db: AsyncSession, asset_ids: Iterable[int], *, subject_id: int
) -> dict[int, StoredImage]:
    """为导出预取同学科的内容图片;找不到或跨学科的 id 不返回(渲染时退化为 alt)。"""
    ids = sorted(set(asset_ids))
    if not ids:
        return {}
    rows = await db.scalars(
        select(MediaAsset).where(
            MediaAsset.id.in_(ids),
            MediaAsset.purpose == MediaPurpose.CONTENT.value,
            MediaAsset.subject_id == subject_id,
        )
    )
    return {
        asset.id: StoredImage(path=storage.object_path(asset.sha256), mime=asset.mime)
        for asset in rows.all()
        if storage.exists(asset.sha256)
    }
