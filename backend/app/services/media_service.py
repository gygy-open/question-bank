"""媒体资产的唯一写入口与读取鉴权。

所有上传、导入、识别产生的媒体都经 ingest 入库:服务端按文件内容识别类型、按 sha256
去重、文件落到内容寻址存储;业务代码只持有资产 id。
"""
from __future__ import annotations

import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import unquote

from PIL import Image, UnidentifiedImageError
from mutagen import File as MutagenFile, MutagenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Forbidden, NotFound, Unprocessable
from app.core import permissions, storage
from app.core.config import settings
from app.core.file_paths import resolve_within
from app.core.permissions import Permission
from app.models.media_asset import LegacyMediaPath, MediaAsset, MediaKind, MediaPurpose, MediaStatus
from app.models.user import User
from app.core.api_errors import ErrorCode

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_AUDIO_BYTES = 100 * 1024 * 1024

WEB_IMAGE_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
# 不转码:只收浏览器可直接播放的格式。
WEB_AUDIO_MIMES = frozenset({"audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav"})
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
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
}
_MIME_BY_EXTENSION = {ext: mime for mime, ext in _EXTENSION_BY_MIME.items()} | {".jpeg": "image/jpeg", ".tiff": "image/tiff"}


@dataclass(frozen=True)
class SniffResult:
    kind: str
    mime: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None


_MP4_AUDIO_BRANDS = (b"M4A ", b"M4B ", b"mp42", b"mp41", b"isom", b"iso2")


def _sniff_audio_mime(data: bytes) -> Optional[str]:
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return "audio/mpeg"
    if data[4:8] == b"ftyp" and data[8:12] in _MP4_AUDIO_BRANDS:
        return "audio/mp4"
    if data[:4] == b"OggS":
        return "audio/ogg"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav"
    return None


def _sniff_audio(data: bytes, mime: str) -> SniffResult:
    try:
        parsed = MutagenFile(io.BytesIO(data))
    except (MutagenError, ValueError, OSError) as exc:
        raise Unprocessable("无法识别的音频文件", ErrorCode.MEDIA_AUDIO_UNRECOGNIZED) from exc
    length = getattr(getattr(parsed, "info", None), "length", None)
    if not length or length <= 0:
        raise Unprocessable("无法识别的音频文件", ErrorCode.MEDIA_AUDIO_UNRECOGNIZED)
    return SniffResult(kind=MediaKind.AUDIO.value, mime=mime, duration=round(float(length), 3))


def _sniff_metafile(data: bytes) -> Optional[str]:
    if data[:4] == b"\x01\x00\x00\x00" and data[40:44] == b" EMF":
        return "image/emf"
    if data[:4] == b"\xd7\xcd\xc6\x9a":
        return "image/wmf"
    if data[:2] in (b"\x01\x00", b"\x02\x00") and data[2:4] == b"\x09\x00":
        return "image/wmf"
    return None


def sniff(data: bytes, *, allow_legacy_formats: bool = False, allow_audio: bool = False) -> SniffResult:
    """按文件内容识别媒体类型;不在白名单内一律拒绝。"""
    audio_mime = _sniff_audio_mime(data)
    if audio_mime is not None:
        if not allow_audio:
            raise Unprocessable("这里只能上传图片", ErrorCode.MEDIA_IMAGE_ONLY)
        return _sniff_audio(data, audio_mime)
    metafile = _sniff_metafile(data)
    if metafile is not None:
        if not allow_legacy_formats:
            raise Unprocessable("不支持的图片格式，请上传 PNG、JPEG、GIF 或 WebP", ErrorCode.MEDIA_IMAGE_FORMAT_UNSUPPORTED)
        return SniffResult(kind=MediaKind.IMAGE.value, mime=metafile)
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format or ""
            width, height = img.size
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise Unprocessable("无法识别的文件，请上传 PNG、JPEG、GIF 或 WebP 图片", ErrorCode.MEDIA_FILE_UNRECOGNIZED) from exc
    mime = _PIL_WEB_FORMATS.get(fmt)
    if mime is None and allow_legacy_formats:
        mime = _PIL_LEGACY_FORMATS.get(fmt)
    if mime is None:
        raise Unprocessable("不支持的图片格式，请上传 PNG、JPEG、GIF 或 WebP", ErrorCode.MEDIA_IMAGE_FORMAT_UNSUPPORTED)
    return SniffResult(kind=MediaKind.IMAGE.value, mime=mime, width=width, height=height)


def is_displayable(mime: str) -> bool:
    """浏览器能否直接显示(图片)或播放(音频)。"""
    return mime in WEB_IMAGE_MIMES or mime in WEB_AUDIO_MIMES


def extension_for(mime: str) -> str:
    return _EXTENSION_BY_MIME.get(mime, "")


def content_url(asset_id: int) -> str:
    return f"{settings.API_V1_STR}/media/{asset_id}/content"


def asset_id_from_url(url: Any) -> Optional[int]:
    """content_url() 的逆运算;不是资产内容 URL 时返回 None。"""
    if not isinstance(url, str):
        return None
    prefix, suffix = f"{settings.API_V1_STR}/media/", "/content"
    if not (url.startswith(prefix) and url.endswith(suffix)):
        return None
    raw = url[len(prefix):-len(suffix)]
    return int(raw) if raw.isdigit() and not raw.startswith("0") else None


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
    allow_audio: bool = False,
    max_bytes: Optional[int] = None,
) -> MediaAsset:
    """识别、去重并登记一个资产;只 flush,由调用方决定何时提交。max_bytes 为图片上限。"""
    max_bytes = max_bytes or MAX_IMAGE_BYTES
    if purpose == MediaPurpose.CONTENT and subject_id is None:
        raise Unprocessable("题目内容图片必须归属学科", ErrorCode.MEDIA_SUBJECT_REQUIRED)
    if purpose != MediaPurpose.CONTENT and actor_id is None:
        raise Unprocessable("个人媒体必须归属用户", ErrorCode.MEDIA_OWNER_REQUIRED)
    limit = max(max_bytes, MAX_AUDIO_BYTES) if allow_audio else max_bytes
    if len(data) > limit:
        raise Unprocessable(
            f"文件过大（上限 {limit // (1024 * 1024)} MB）",
            ErrorCode.MEDIA_FILE_TOO_LARGE,
            {"limit_mb": limit // (1024 * 1024)},
        )
    if not data:
        raise Unprocessable("文件为空", ErrorCode.MEDIA_FILE_EMPTY)

    info = sniff(data, allow_legacy_formats=allow_legacy_formats, allow_audio=allow_audio)
    if info.kind == MediaKind.IMAGE.value and len(data) > max_bytes:
        raise Unprocessable(
            f"图片过大（上限 {max_bytes // (1024 * 1024)} MB）",
            ErrorCode.MEDIA_IMAGE_TOO_LARGE,
            {"limit_mb": max_bytes // (1024 * 1024)},
        )
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
        duration=info.duration,
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
        raise NotFound("Media not found", ErrorCode.MEDIA_NOT_FOUND)
    return asset


async def get_owned_chat_asset(db: AsyncSession, asset_id: int, user: User) -> MediaAsset:
    asset = await db.get(MediaAsset, asset_id)
    if asset is None or asset.purpose != MediaPurpose.CHAT.value or asset.owner_user_id != user.id:
        raise Forbidden("Media not accessible", ErrorCode.MEDIA_NOT_ACCESSIBLE)
    return asset


def iter_image_attrs(value: Any) -> Iterator[dict]:
    """遍历任意嵌套 RichDoc / 快照 JSON 中的图片节点 attrs(可就地修改)。"""
    return iter_media_attrs(value, types=("image",))


def iter_media_attrs(value: Any, types: tuple[str, ...] = ("image", "audio")) -> Iterator[dict]:
    """遍历任意嵌套 RichDoc / 快照 JSON 中引用媒体的节点 attrs(可就地修改)。"""
    stack: list[Any] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("type") in types and isinstance(node.get("attrs"), dict):
                yield node["attrs"]
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)


def collect_asset_ids(value: Any) -> set[int]:
    """在任意嵌套 RichDoc / 快照 JSON 中收集图片与音频节点引用的资产 id。"""
    found: set[int] = set()
    for attrs in iter_media_attrs(value):
        asset_id = attrs.get("assetId")
        if isinstance(asset_id, int) and not isinstance(asset_id, bool) and asset_id > 0:
            found.add(asset_id)
    return found


LEGACY_MEDIA_PREFIX = "/static/media/"


def normalize_legacy_path(src: Any) -> Optional[str]:
    """旧媒体 URL 规整为映射表键(去掉 query/fragment、URL 解码);不是旧媒体 URL 返回 None。"""
    if not isinstance(src, str) or not src.startswith(LEGACY_MEDIA_PREFIX):
        return None
    path = unquote(src.split("#", 1)[0].split("?", 1)[0])
    return path if len(path) > len(LEGACY_MEDIA_PREFIX) else None


def collect_legacy_paths(value: Any) -> set[str]:
    found: set[str] = set()
    for attrs in iter_image_attrs(value):
        path = normalize_legacy_path(attrs.get("src"))
        if path:
            found.add(path)
    return found


def legacy_media_file(path: str) -> Optional[Path]:
    """旧媒体目录中的原文件(迁移前/清理前);路径必须仍在媒体目录内。"""
    real = resolve_within(settings.MEDIA_DIR, settings.MEDIA_DIR / path[len(LEGACY_MEDIA_PREFIX):])
    return real if real is not None and real.is_file() else None


async def resolve_legacy_images(db: AsyncSession, paths: Iterable[str]) -> dict[str, StoredImage]:
    """旧 URL → 本机文件:优先迁移映射(对象存储),其次旧目录原文件;都找不到的不返回。"""
    wanted = sorted({p for p in (normalize_legacy_path(p) for p in paths) if p})
    if not wanted:
        return {}
    rows = await db.scalars(select(LegacyMediaPath).where(LegacyMediaPath.old_path.in_(wanted)))
    resolved = {
        row.old_path: StoredImage(path=storage.object_path(row.sha256), mime=row.mime)
        for row in rows.all()
        if storage.exists(row.sha256)
    }
    for path in wanted:
        if path in resolved:
            continue
        real = legacy_media_file(path)
        if real is not None:
            resolved[path] = StoredImage(path=real, mime=_MIME_BY_EXTENSION.get(real.suffix.lower(), "application/octet-stream"))
    return resolved


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
