from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.crud.base import CRUDBase
from app.models.ai_config import AIProvider, AIModel
from app.schemas.ai_config import AIProviderCreate, AIProviderUpdate, AIModelCreate, AIModelUpdate

class CRUDAIProvider(CRUDBase[AIProvider, AIProviderCreate, AIProviderUpdate]):
    # 写操作走 app.services.ai_config_service(负责 Key 加密与归属校验)。
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
