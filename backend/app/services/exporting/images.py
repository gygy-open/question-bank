"""图片路径解析:RichDoc 里的 /static/media/... → 本机绝对路径。

LaTeX 渲染器把文件拷进 images/ 并改写为相对路径;DOCX 渲染器直接从绝对路径嵌入。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.core.file_paths import resolve_within

logger = logging.getLogger(__name__)

_MEDIA_PREFIX = "/static/media/"


class ImageResolver:
    """把 RichDoc image 节点的 src 解析为本机可读文件路径。"""

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
