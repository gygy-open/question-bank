from typing import List
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud.base import CRUDBase
from app.models.prompt import PromptTemplate
from app.schemas.prompt import PromptTemplateCreate, PromptTemplateUpdate

class CRUDPromptTemplate(CRUDBase[PromptTemplate, PromptTemplateCreate, PromptTemplateUpdate]):
    async def create(self, db: AsyncSession, *, obj_in: PromptTemplateCreate, user_id: int) -> PromptTemplate:
        obj_in_data = jsonable_encoder(obj_in)
        db_obj = self.model(**obj_in_data, user_id=user_id)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_by_user(self, db: AsyncSession, *, user_id: int, skip: int = 0, limit: int = 100) -> List[PromptTemplate]:
        query = select(PromptTemplate).where(PromptTemplate.user_id == user_id).offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

prompt_template = CRUDPromptTemplate(PromptTemplate)
