from typing import Optional, Union, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.crud.base import CRUDBase
from app.models.tag import Tag
from app.schemas.tag import TagCreate, TagUpdate
from app.services.activity_logger import log_activity

class CRUDTag(CRUDBase[Tag, TagCreate, TagUpdate]):
    async def get_multi_by_subject(
        self, db: AsyncSession, *, subject_id: int, skip: int = 0, limit: Optional[int] = 100
    ) -> List[Tag]:
        query = select(self.model).where(self.model.subject_id == subject_id).offset(skip)
        if limit is not None:
            query = query.limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    async def get_by_name_in_subject(
        self, db: AsyncSession, *, name: str, subject_id: int
    ) -> Optional[Tag]:
        result = await db.execute(
            select(self.model).where(
                self.model.name == name, self.model.subject_id == subject_id
            )
        )
        return result.scalar_one_or_none()

    async def create(self, db: AsyncSession, *, obj_in: TagCreate, user_id: Optional[int] = None) -> Tag:
        db_obj = Tag(**obj_in.model_dump())
        if user_id:
            db_obj.created_by = user_id
            db_obj.updated_by = user_id
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        await log_activity(db, user_id, "create", "tag", db_obj.id, details=obj_in.model_dump())
        await db.commit()
        return db_obj

    async def update(
        self, db: AsyncSession, *, db_obj: Tag, obj_in: Union[TagUpdate, Dict[str, Any]], user_id: Optional[int] = None
    ) -> Tag:
        if user_id:
            db_obj.updated_by = user_id
        # subject_id 不允许通过更新迁移，避免跨学科命名冲突
        if isinstance(obj_in, dict):
            obj_in.pop("subject_id", None)
        updated_obj = await super().update(db, db_obj=db_obj, obj_in=obj_in)
        details = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        await log_activity(db, user_id, "update", "tag", updated_obj.id, details=details)
        await db.commit()
        return updated_obj

    async def remove(self, db: AsyncSession, *, id: int, user_id: Optional[int] = None) -> Tag:
        obj = await db.get(self.model, id)
        if obj:
            await db.delete(obj)
            await db.commit()
            await log_activity(db, user_id, "delete", "tag", id)
            await db.commit()
        return obj

tag = CRUDTag(Tag)
