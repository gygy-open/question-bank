from typing import Optional, Union, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.subject import Subject
from app.schemas.subject import SubjectCreate, SubjectUpdate
from app.services.activity_logger import log_activity

class CRUDSubject(CRUDBase[Subject, SubjectCreate, SubjectUpdate]):
    async def create(self, db: AsyncSession, *, obj_in: SubjectCreate, user_id: Optional[int] = None) -> Subject:
        db_obj = Subject(**obj_in.model_dump())
        if user_id:
            db_obj.created_by = user_id
            db_obj.updated_by = user_id
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        await log_activity(db, user_id, "create", "subject", db_obj.id, details=obj_in.model_dump())
        await db.commit()
        return db_obj

    async def update(
        self, db: AsyncSession, *, db_obj: Subject, obj_in: Union[SubjectUpdate, Dict[str, Any]], user_id: Optional[int] = None
    ) -> Subject:
        if user_id:
            db_obj.updated_by = user_id
        updated_obj = await super().update(db, db_obj=db_obj, obj_in=obj_in)
        details = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        await log_activity(db, user_id, "update", "subject", updated_obj.id, details=details)
        await db.commit()
        return updated_obj

    async def remove(self, db: AsyncSession, *, id: int, user_id: Optional[int] = None) -> Subject:
        obj = await db.get(self.model, id)
        if obj:
            await db.delete(obj)
            await db.commit()
            await log_activity(db, user_id, "delete", "subject", id)
            await db.commit()
        return obj

subject = CRUDSubject(Subject)
