"""导入流程与媒体资产的衔接:抽取出的图片入库为内容资产,源文件存入对象存储。"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.errors import Unprocessable
from app.core.config import settings
from app.models.media_asset import MediaPurpose
from app.services import media_service

logger = logging.getLogger(__name__)

_SOURCE_REF_RE = re.compile(r"^([0-9a-f]{64})\.([0-9a-f]{64})$")


class ImportImageSink:
    """把导入文档里的图片登记为本学科内容资产,返回可写进 markdown 的 URL。"""

    def __init__(self, db: AsyncSession, *, subject_id: Optional[int], actor_id: Optional[int]) -> None:
        self.db = db
        self.subject_id = subject_id
        self.actor_id = actor_id

    async def store(self, data: bytes, filename: str) -> Optional[str]:
        if self.subject_id is None:
            raise Unprocessable("导入含图片的文档前请先选择学科")
        try:
            asset = await media_service.ingest(
                self.db,
                data,
                purpose=MediaPurpose.CONTENT,
                subject_id=self.subject_id,
                actor_id=self.actor_id,
                filename=filename,
                allow_legacy_formats=True,
            )
        except Unprocessable as exc:
            # 单张图片无法入库不应中断整份文档的导入;该引用保持原样(显示为坏图/alt)。
            logger.warning("Skipping unsupported imported image %s: %s", filename, exc.detail)
            return None
        return media_service.content_url(asset.id)


def _source_signature(sha256: str, user_id: int) -> str:
    message = f"import-source:{sha256}:{user_id}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()


def sign_source_ref(sha256: str, user_id: int) -> str:
    """同步导入返回给前端的源文件凭据;提交时校验,前端无法伪造指向他人文件的引用。"""
    return f"{sha256}.{_source_signature(sha256, user_id)}"


def verify_source_ref(ref: Optional[str], user_id: int) -> Optional[str]:
    match = _SOURCE_REF_RE.match(ref or "")
    if match is None:
        return None
    sha256, signature = match.groups()
    if not hmac.compare_digest(signature, _source_signature(sha256, user_id)):
        return None
    return sha256
