"""System health endpoints.

Two audiences share this router:

* the **orchestrator** — ``GET /health`` and ``GET /health/ready`` are unauthenticated
  readiness probes that must stay cheap and dependency-accurate;
* the **operator** — the «بررسی سلامت» module (M5): upstream observations per provider,
  the check history and «اجرای بررسی», which probe every enabled provider through the
  real adapters.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import SessionDep
from app.auth.dependencies import client_ip, require_roles, user_agent
from app.health.service import readiness
from app.models.enums import AdminRole, HealthStatus
from app.models.identity import AdminUser
from app.schemas.common import ApiModel
from app.schemas.health import ReadinessResponse
from app.services.health_admin import HealthAdminService

router = APIRouter(prefix="/health", tags=["health"])

READ_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR, AdminRole.VIEWER)
ACTION_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR)


class ProviderHealthRead(ApiModel):
    provider_id: uuid.UUID
    name: str
    slug: str
    enabled: bool
    status: HealthStatus
    last_checked_at: datetime | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    requests: int = 0
    errors: int = 0
    error_rate: float = 0.0
    avg_latency_ms: int | None = None
    uptime_percent: float | None = None
    credential_count: int = 0
    model_count: int = 0


class HealthObservationRead(ApiModel):
    id: uuid.UUID
    target_type: str
    target_id: uuid.UUID
    provider_id: uuid.UUID | None = None
    credential_id: uuid.UUID | None = None
    model_id: uuid.UUID | None = None
    endpoint_id: uuid.UUID | None = None
    status: HealthStatus
    latency_ms: int | None = None
    status_code: int | None = None
    error_code: str | None = None
    checked_at: datetime


class CheckRunResponse(ApiModel):
    checked: int
    statuses: dict[str, int]
    duration_ms: int
    started_at: datetime
    failures: list[dict]


@router.get("", response_model=ReadinessResponse)
async def system_health() -> ReadinessResponse:
    """Readiness probe: database, Redis and application runtime."""
    return await readiness()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_required() -> ReadinessResponse:
    """Strict readiness probe used by orchestrators (503 when a component is down)."""
    return await readiness(require_healthy=True)


@router.get("/providers", response_model=list[ProviderHealthRead])
async def provider_health(
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> list[ProviderHealthRead]:
    """Latest status, latency, error rate and 24h uptime per provider."""
    rows = await HealthAdminService(session).overview()
    return [ProviderHealthRead(**row.__dict__) for row in rows]


@router.get("/observations", response_model=list[HealthObservationRead])
async def health_observations(
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    provider_id: Annotated[uuid.UUID | None, Query()] = None,
    target_type: Annotated[
        str | None, Query(description="provider|credential|model|endpoint")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[HealthObservationRead]:
    """Observation history, newest first — what «آخرین بررسی» actually recorded."""
    rows = await HealthAdminService(session).history(
        provider_id=provider_id, target_type=target_type, limit=limit
    )
    return [
        HealthObservationRead(
            id=row.id,
            target_type=row.target_type.value,
            target_id=row.target_id,
            provider_id=row.provider_id,
            credential_id=row.credential_id,
            model_id=row.model_id,
            endpoint_id=row.endpoint_id,
            status=HealthStatus(row.status),
            latency_ms=row.latency_ms,
            status_code=row.status_code,
            error_code=row.error_code,
            checked_at=row.checked_at,
        )
        for row in rows
    ]


@router.post("/checks", response_model=CheckRunResponse)
async def run_health_checks(
    request: Request,
    session: SessionDep,
    current_user: AdminUser = Depends(require_roles(*ACTION_ROLES)),
    provider_id: Annotated[uuid.UUID | None, Query()] = None,
) -> CheckRunResponse:
    """«اجرای بررسی» — probe the enabled providers now and store the observations."""
    outcome = await HealthAdminService(session).run_checks(
        actor=current_user,
        provider_id=provider_id,
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    return CheckRunResponse(
        checked=outcome.checked,
        statuses=outcome.statuses,
        duration_ms=outcome.duration_ms,
        started_at=outcome.started_at,
        failures=outcome.failures,
    )
