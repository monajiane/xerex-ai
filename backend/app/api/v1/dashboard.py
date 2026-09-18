"""Dashboard aggregates."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import SessionDep
from app.auth.dependencies import get_current_user
from app.models.identity import AdminUser
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
async def summary(
    session: SessionDep,
    _: AdminUser = Depends(get_current_user),
) -> DashboardSummary:
    """KPI cards, provider health strip and top models (24h window)."""
    return await DashboardService(session).summary()
