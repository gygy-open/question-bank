from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.tag_category import TagCategory
from app.schemas.tag_category import TagCategoryCreate, TagCategoryUpdate

class CRUDTagCategory(CRUDBase[TagCategory, TagCategoryCreate, TagCategoryUpdate]):
    async def get_multi_by_subject(
        self, db: AsyncSession, *, subject_id: int, skip: int = 0, limit: Optional[int] = 100
    ) -> List[TagCategory]:
        query = select(self.model).where(self.model.subject_id == subject_id).order_by(self.model.sort_order.asc(), self.model.id.asc()).offset(skip)
        if limit is not None:
            query = query.limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    async def get_by_name_in_subject(
        self, db: AsyncSession, *, name: str, subject_id: int
    ) -> Optional[TagCategory]:
        result = await db.execute(
            select(self.model).where(
                self.model.name == name, self.model.subject_id == subject_id
            )
        )
        return result.scalar_one_or_none()

tag_category = CRUDTagCategory(TagCategory)
