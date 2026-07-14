from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud, schemas
from app.api import deps
from app.schemas.user import User

router = APIRouter()

@router.get("", response_model=schemas.ActivityLogPage)
async def read_activity_logs(
    db: AsyncSession = Depends(deps.get_db),
    page: int = 1,
    size: int = 20,
    user_id: Optional[int] = None,
    current_user: User = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Retrieve activity logs.
    """
    if current_user.id != 1:
        raise HTTPException(status_code=403, detail="Only the super administrator can access this resource")

    skip = (page - 1) * size
    logs, total = await crud.activity_log.get_multi_with_user_and_count(db, skip=skip, limit=size, user_id=user_id)
    
    import math
    pages = math.ceil(total / size) if size > 0 else 0
    
    return schemas.ActivityLogPage(
        items=logs,
        total=total,
        page=page,
        size=size,
        pages=pages
    )
