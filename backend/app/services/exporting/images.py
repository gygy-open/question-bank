"""图片解析:RichDoc image 节点(assetId 或旧 /static/media src) → 本机文件。

LaTeX 渲染器把文件拷进 images/ 并改写为相对路径;DOCX 渲染器直接从文件嵌入。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from app.core.config import settings
from app.core.file_paths import resolve_within
from app.services.media_service import StoredImage, normalize_legacy_path

logger = logging.getLogger(__name__)

_MEDIA_PREFIX = "/static/media/"


@dataclass(frozen=True)
class ResolvedImage:
    path: Path
    # 同一图片在一次导出内只拷贝一次;key 用于去重,suffix 用于需要扩展名的格式(LaTeX)。
    key: str
    suffix: str


class ImageResolver:
    """把 RichDoc image 节点解析为本机可读文件:优先 assetId(需预取),其次旧 /static/media src。"""

    def __init__(
        self,
        assets: Optional[Mapping[int, StoredImage]] = None,
        legacy: Optional[Mapping[str, StoredImage]] = None,
    ) -> None:
        self.assets = dict(assets or {})
        # 旧 /static/media URL(规整后)→ 文件,由 media_service.resolve_legacy_images 预取。
        self.legacy = dict(legacy or {})

    def resolve_image(self, attrs: Mapping[str, Any]) -> Optional[ResolvedImage]:
        asset_id = attrs.get("assetId")
        stored = self.assets.get(asset_id) if isinstance(asset_id, int) else None
        if stored is not None:
            return ResolvedImage(path=stored.path, key=f"asset-{asset_id}", suffix=stored.extension)
        src = str(attrs.get("src") or "")
        legacy_key = normalize_legacy_path(src)
        stored = self.legacy.get(legacy_key) if legacy_key else None
        if stored is not None:
            return ResolvedImage(path=stored.path, key=legacy_key, suffix=stored.extension or stored.path.suffix)
        path = self.resolve(src)
        if path is None:
            return None
        return ResolvedImage(path=path, key=src, suffix=path.suffix)

    def resolve(self, src: str) -> Optional[Path]:
        if not src or not src.startswith(_MEDIA_PREFIX):
            return None
        abs_path = resolve_within(settings.MEDIA_DIR, settings.MEDIA_DIR / src[len(_MEDIA_PREFIX):])
        if abs_path is None:
            logger.warning("Rejected image path outside media dir: %s", src)
            return None
        if abs_path.is_file():
            return abs_path
        return None
