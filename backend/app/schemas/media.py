from datetime import datetime
from typing import Optional

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
