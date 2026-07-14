from sqlalchemy.ext.asyncio import AsyncSession
from app.models.activity_log import ActivityLog
from typing import Any, Optional
import json
from fastapi.encoders import jsonable_encoder

async def log_activity(
    db: AsyncSession,
    user_id: Optional[int],
    action: str,
    resource_type: str,
    resource_id: Optional[int] = None,
    details: Any = None,
    ip_address: Optional[str] = None
):
    """
    记录用户行为
    """
    if details:
        try:
            # Ensure details is JSON serializable
            details = jsonable_encoder(details)
        except:
            details = str(details)

    log = ActivityLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address
    )
    db.add(log)
    # We don't commit here, we let the caller commit or we commit if needed.
    # Usually logging happens within the same transaction or a separate one.
    # For simplicity, let's assume it's part of the same transaction.
    # But if the main transaction fails, we might lose the log?
    # Or if we want to log failures?
    # For now, let's just add to session.
    return log
