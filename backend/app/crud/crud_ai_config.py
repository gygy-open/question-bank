from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.crud.base import CRUDBase
from app.models.ai_config import AIProvider, AIModel
from app.schemas.ai_config import AIProviderCreate, AIProviderUpdate, AIModelCreate, AIModelUpdate

class CRUDAIProvider(CRUDBase[AIProvider, AIProviderCreate, AIProviderUpdate]):
    async def create_with_models(self, db: AsyncSession, *, obj_in: AIProviderCreate) -> AIProvider:
        db_obj = AIProvider(
            name=obj_in.name,
            interface_type=obj_in.interface_type,
            base_url=obj_in.base_url,
            api_key=obj_in.api_key,
            is_active=obj_in.is_active
        )
        db.add(db_obj)
        await db.flush() # Get ID
        
        for model_in in obj_in.models:
            db_model = AIModel(
                provider_id=db_obj.id,
                name=model_in.name,
                is_vision_capable=model_in.is_vision_capable,
                is_embedding_model=model_in.is_embedding_model
            )
            db.add(db_model)
        
        await db.commit()
        await db.refresh(db_obj)
        # Re-fetch with models loaded
        query = select(AIProvider).options(selectinload(AIProvider.models)).where(AIProvider.id == db_obj.id)
        result = await db.execute(query)
        return result.scalar_one()

    async def get_multi_with_models(self, db: AsyncSession, *, skip: int = 0, limit: int = 100) -> List[AIProvider]:
        query = select(AIProvider).options(selectinload(AIProvider.models)).offset(skip).limit(limit)
        result = await db.execute(query)
        return result.scalars().all()

    async def get_with_models(self, db: AsyncSession, id: int) -> Optional[AIProvider]:
        query = select(AIProvider).options(selectinload(AIProvider.models)).where(AIProvider.id == id)
        result = await db.execute(query)
        return result.scalar_one_or_none()

class CRUDAIModel(CRUDBase[AIModel, AIModelCreate, AIModelUpdate]):
    async def get_by_provider(self, db: AsyncSession, provider_id: int) -> List[AIModel]:
        query = select(AIModel).where(AIModel.provider_id == provider_id)
        result = await db.execute(query)
        return result.scalars().all()

ai_provider = CRUDAIProvider(AIProvider)
ai_model = CRUDAIModel(AIModel)
