"""System health endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from app.health.service import readiness
from app.schemas.health import ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=ReadinessResponse)
async def system_health() -> ReadinessResponse:
    """Readiness probe: database, Redis and application runtime."""
    return await readiness()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_required() -> ReadinessResponse:
    """Strict readiness probe used by orchestrators (503 when a component is down)."""
    return await readiness(require_healthy=True)
