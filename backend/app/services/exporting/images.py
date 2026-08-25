"""图片路径解析:RichDoc 里的 /static/media/... → 本机绝对路径。

LaTeX 渲染器把文件拷进 images/ 并改写为相对路径;DOCX 渲染器直接从绝对路径嵌入。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_MEDIA_PREFIX = "/static/media/"


class ImageResolver:
    """把 RichDoc image 节点的 src 解析为本机可读文件路径。"""

    def resolve(self, src: str) -> Optional[Path]:
        if not src or not src.startswith(_MEDIA_PREFIX):
            return None
        rel = src[len(_MEDIA_PREFIX):]
        try:
            abs_path = (settings.MEDIA_DIR / rel).resolve()
        except Exception as exc:
            logger.warning("Failed to resolve image path %s: %s", src, exc)
            return None
        if abs_path.exists():
            return abs_path
        return None
