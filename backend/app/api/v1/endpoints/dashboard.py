from typing import Any

from fastapi import APIRouter, Depends, Query

from app import models
from app.api import deps
from app.core.permissions import Permission
from app.schemas.dashboard import DashboardContributors, DashboardStats
from app.services import dashboard_service

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def read_dashboard_stats(
    db: deps.SessionDep,
    subject_id: int,
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    return await dashboard_service.get_dashboard_stats(db, subject_id=subject_id, viewer=current_user)


@router.get("/contributors", response_model=DashboardContributors)
async def read_dashboard_contributors(
    db: deps.SessionDep,
    subject_id: int,
    days: int = Query(30, ge=1, le=365),
    current_user: models.User = Depends(deps.get_current_active_user),
) -> Any:
    deps.require(current_user, Permission.VIEW_QUESTION, subject_id=subject_id)
    return await dashboard_service.get_contributors(
        db, subject_id=subject_id, viewer=current_user, days=days
    )
