"""System information, capabilities and the delivery roadmap."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_user
from app.models.identity import AdminUser
from app.schemas.system import RoadmapResponse, SystemInfo
from app.services import system as system_service

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/info", response_model=SystemInfo)
async def info() -> SystemInfo:
    """Public runtime metadata (no secrets)."""
    return system_service.system_info()


@router.get("/roadmap", response_model=RoadmapResponse)
async def roadmap(_: AdminUser = Depends(get_current_user)) -> RoadmapResponse:
    """Planned API surface per milestone, used by the panel's placeholder screens."""
    return system_service.roadmap()
