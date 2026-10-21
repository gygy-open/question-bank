from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

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


class MediaAssetUpdate(BaseModel):
    original_filename: Optional[str] = Field(default=None, max_length=255)
    alt: Optional[str] = Field(default=None, max_length=500)
    source: Optional[str] = Field(default=None, max_length=255)


class MediaReplaceTarget(BaseModel):
    owner_type: Literal["question", "stimulus", "composition"]
    owner_id: int


class MediaReplaceRequest(BaseModel):
    new_asset_id: int
    # 缺省 = 全部可编辑的引用方。
    targets: Optional[List[MediaReplaceTarget]] = None


class MediaReplaceResult(BaseModel):
    replaced: List[MediaReplaceTarget]
    skipped: int = 0
    frozen: int = 0


class MediaBatchIds(BaseModel):
    ids: List[int] = Field(min_length=1, max_length=100)


class MediaBatchSourceUpdate(MediaBatchIds):
    source: Optional[str] = Field(default=None, max_length=255)


class MediaBatchResult(BaseModel):
    affected: int
    skipped: int = 0


class MediaCopyRequest(BaseModel):
    subject_id: int


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
