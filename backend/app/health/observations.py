"""Health observations that must survive a failed unit of work.

The request session is deliberately one transaction per request: services never
commit, and an error response rolls everything back. That is the right default, but
it is wrong for one kind of write: health is a statement about the *outside world*
("this provider answered 401 at 10:12"), not about the administration request. If a
discovery run fails with a provider error, that observation is exactly what the
operator needs to see afterwards — so it is persisted in its own short transaction
before the typed error is raised.
"""

from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.database.session import session_scope
from app.health.targets import HealthTarget, record_health_check
from app.models.enums import HealthStatus
from app.models.providers import Provider

logger = get_logger(__name__)


async def record_failure_observation(
    *targets: HealthTarget,
    status: HealthStatus,
    provider_id: uuid.UUID | None = None,
    latency_ms: int | None = None,
    status_code: int | None = None,
    error_code: str | None = None,
) -> None:
    """Append the observation(s) in their own transaction and roll up the provider."""
    try:
        async with session_scope() as session:
            for target in targets:
                await record_health_check(
                    session,
                    target,
                    status=status,
                    latency_ms=latency_ms,
                    status_code=status_code,
                    error_code=error_code,
                )
            if provider_id is not None:
                provider = await session.get(Provider, provider_id)
                if provider is not None:
                    provider.health_status = status.value
    except Exception:  # pragma: no cover - never fail the response because of telemetry
        logger.warning("failure_observation_not_recorded", extra={"error_code": error_code})


__all__ = ["record_failure_observation"]
