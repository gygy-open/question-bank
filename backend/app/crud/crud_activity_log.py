from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.crud.base import CRUDBase
from app.models.activity_log import ActivityLog
from app.schemas.activity_log import ActivityLogCreate, ActivityLog as ActivityLogSchema

class CRUDActivityLog(CRUDBase[ActivityLog, ActivityLogCreate, ActivityLogCreate]):
    async def get_multi_with_user_and_count(
        self, db: AsyncSession, *, skip: int = 0, limit: int = 100, user_id: Optional[int] = None
    ) -> tuple[List[ActivityLog], int]:
        from sqlalchemy import func
        
        # Base query construction
        query = select(self.model)
        if user_id:
            query = query.filter(self.model.user_id == user_id)

        # Count query
        # We use select(func.count()).select_from(query.subquery()) or just build a count query with same filters
        count_query = select(func.count()).select_from(self.model)
        if user_id:
            count_query = count_query.filter(self.model.user_id == user_id)
            
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0
        
        # Data query
        query = query.order_by(desc(self.model.created_at)).offset(skip).limit(limit)
        from sqlalchemy.orm import selectinload
        query = query.options(selectinload(self.model.user))
        
        result = await db.execute(query)
        items = result.scalars().all()
        
        return items, total

activity_log = CRUDActivityLog(ActivityLog)
