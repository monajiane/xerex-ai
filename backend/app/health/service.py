"""System health aggregation for the admin panel.

Component statuses are English enum values (``healthy`` | ``degraded`` | ``down``);
the Persian UI renders «سالم» / «کاهش‌یافته» / «قطع» (see PROMPT.md 14.9).
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import settings
from app.core.errors import DependencyUnavailableError
from app.database.redis import check_redis
from app.database.session import check_database
from app.health.state import uptime_seconds
from app.schemas.health import ComponentHealth, ReadinessResponse

_REQUIRED_COMPONENTS = ("database",)
_DEEP_PROBE_SECONDS = 4.0


async def probe_components() -> list[ComponentHealth]:
    database = ComponentHealth(**await check_database())
    redis_component = ComponentHealth(**await check_redis())
    return [database, redis_component]


def overall_status(components: list[ComponentHealth]) -> str:
    required_down = any(
        component.status == "down" and component.name in _REQUIRED_COMPONENTS
        for component in components
    )
    if required_down:
        return "down"
    if any(component.status in {"down", "degraded"} for component in components):
        return "degraded"
    return "healthy"


async def readiness(*, require_healthy: bool = False) -> ReadinessResponse:
    components = await probe_components()
    status = overall_status(components)
    if require_healthy and status == "down":
        raise DependencyUnavailableError(
            "A required component is unavailable.",
            code="component_down",
            details={"components": [c.model_dump() for c in components]},
        )
    return ReadinessResponse(
        status=status,  # type: ignore[arg-type]
        service=settings.app_name,
        version=settings.app_version,
        milestone=settings.milestone,
        environment=settings.environment,
        checked_at=datetime.now(UTC),
        uptime_seconds=uptime_seconds(),
        components=components,
    )
