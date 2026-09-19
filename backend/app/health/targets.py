"""Typed health targets: the data abstraction the routing engine will consume.

Milestone rule: build the model now, keep the workers for later. Nothing in this
module schedules anything — it only makes it impossible to write ambiguous health
data, and it keeps the generic ``target_type``/``target_id`` pointer in sync with
the typed foreign keys.

Example the schema can express (and tests exercise):

===================  ==============
Provider X           healthy
Credential 1         rate_limited
Credential 2         healthy
Model A              healthy
Endpoint A           degraded
===================  ==============
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import HealthStatus, HealthTargetType
from app.models.health import HealthCheck

#: Every dimension the platform tracks. Used by docs, the API and tests.
HEALTH_TARGET_KINDS: tuple[str, ...] = tuple(kind.value for kind in HealthTargetType)


@dataclass(frozen=True)
class HealthTarget:
    """One health dimension instance, e.g. "credential 1 of provider X".

    ``id`` mirrors the pointed-to row so the legacy ``target_id`` column stays
    populated; the typed columns carry referential integrity.
    """

    kind: HealthTargetType
    id: uuid.UUID
    provider_id: uuid.UUID | None = None
    credential_id: uuid.UUID | None = None
    model_id: uuid.UUID | None = None
    endpoint_id: uuid.UUID | None = None

    # -- constructors ----------------------------------------------------
    @classmethod
    def provider(cls, provider_id: uuid.UUID) -> HealthTarget:
        return cls(kind=HealthTargetType.PROVIDER, id=provider_id, provider_id=provider_id)

    @classmethod
    def credential(
        cls, credential_id: uuid.UUID, *, provider_id: uuid.UUID | None = None
    ) -> HealthTarget:
        return cls(
            kind=HealthTargetType.CREDENTIAL,
            id=credential_id,
            credential_id=credential_id,
            provider_id=provider_id,
        )

    @classmethod
    def model(cls, model_id: uuid.UUID, *, provider_id: uuid.UUID | None = None) -> HealthTarget:
        return cls(
            kind=HealthTargetType.MODEL,
            id=model_id,
            model_id=model_id,
            provider_id=provider_id,
        )

    @classmethod
    def endpoint(
        cls,
        endpoint_id: uuid.UUID,
        *,
        model_id: uuid.UUID | None = None,
        provider_id: uuid.UUID | None = None,
        credential_id: uuid.UUID | None = None,
    ) -> HealthTarget:
        return cls(
            kind=HealthTargetType.ENDPOINT,
            id=endpoint_id,
            endpoint_id=endpoint_id,
            model_id=model_id,
            provider_id=provider_id,
            credential_id=credential_id,
        )

    # -- helpers ---------------------------------------------------------
    def typed_columns(self) -> dict[str, uuid.UUID | None]:
        return {
            "provider_id": self.provider_id,
            "credential_id": self.credential_id,
            "model_id": self.model_id,
            "endpoint_id": self.endpoint_id,
        }

    def describe(self) -> dict[str, str | None]:
        """Machine readable identity, used in logs and API payloads."""
        return {"target_type": self.kind.value, "target_id": str(self.id)}


async def record_health_check(
    session: AsyncSession,
    target: HealthTarget,
    *,
    status: HealthStatus,
    latency_ms: int | None = None,
    status_code: int | None = None,
    error_code: str | None = None,
    checked_at: datetime | None = None,
) -> HealthCheck:
    """Append one observation for a provider, credential, model or endpoint."""
    entry = HealthCheck(
        target_type=target.kind,
        target_id=target.id,
        status=status,
        latency_ms=latency_ms,
        status_code=status_code,
        error_code=error_code,
        checked_at=checked_at or datetime.now(UTC),
        **target.typed_columns(),
    )
    session.add(entry)
    await session.flush()
    return entry


async def latest_health_check(session: AsyncSession, target: HealthTarget) -> HealthCheck | None:
    """Most recent observation for one target (no rollup, no caching)."""
    result = await session.execute(
        select(HealthCheck)
        .where(HealthCheck.target_type == target.kind, HealthCheck.target_id == target.id)
        .order_by(HealthCheck.checked_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def health_history(
    session: AsyncSession,
    *,
    kind: HealthTargetType | None = None,
    limit: int = 50,
) -> list[HealthCheck]:
    """Recent observations, newest first, optionally filtered by dimension."""
    statement = select(HealthCheck).order_by(HealthCheck.checked_at.desc()).limit(limit)
    if kind is not None:
        statement = statement.where(HealthCheck.target_type == kind)
    result = await session.execute(statement)
    return list(result.scalars().all())
