from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, computed_field

from app.services import media_service


class MediaAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: Optional[int] = None
    owner_user_id: Optional[int] = None
    purpose: str
    kind: str
    mime: str
    byte_size: int
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[float] = None
    original_filename: Optional[str] = None
    alt: Optional[str] = None
    source: Optional[str] = None
    status: str
    created_at: datetime

    @computed_field
    @property
    def url(self) -> str:
        return media_service.content_url(self.id)

    @computed_field
    @property
    def displayable(self) -> bool:
        return media_service.is_displayable(self.mime)


class MediaAssetListItem(MediaAssetRead):
    usage_count: int = 0


class MediaAssetPage(BaseModel):
    items: List[MediaAssetListItem]
    total: int
    page: int
    size: int


class MediaReferenceItem(BaseModel):
    owner_type: str
    owner_id: int
    title: str
    deleted: bool = False
    # 稿件/定稿版本的跳转信息。
    composition_id: Optional[int] = None
    scope: Optional[str] = None
    version_no: Optional[int] = None


class MediaReferences(BaseModel):
    items: List[MediaReferenceItem]
    # 调用者无权查看的引用方数量(如他人私有题、个人稿件),只给计数不给详情。
    hidden_count: int = 0
