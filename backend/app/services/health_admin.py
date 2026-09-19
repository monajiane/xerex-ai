"""Health observation: scheduled checks, overview and history (M5).

The rules that shape this module:

* a check is an **observation**, never a mutation of the provider configuration: it
  writes a :class:`HealthCheck` row and updates the provider's rolled-up status;
* the same code path serves the scheduler and the «اجرای بررسی» button, so what an
  operator triggers by hand is exactly what runs on a timer;
* aggregates are computed from stored rows (health history + per-attempt usage), never
  estimated. A provider that has never been checked reports ``unknown``, not ``healthy``.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import EncryptionError, decrypt_secret
from app.core.logging import get_logger
from app.database.session import session_scope
from app.health.targets import HealthTarget, record_health_check
from app.models.enums import AuditAction, CredentialStatus, HealthStatus
from app.models.health import HealthCheck
from app.models.identity import AdminUser
from app.models.providers import Model, Provider, ProviderCredential
from app.models.usage import UsageRecord
from app.providers.adapters import build_adapter
from app.services.audit import AuditService

logger = get_logger(__name__)

#: Window used for the error-rate and uptime columns of the overview.
OVERVIEW_WINDOW_HOURS = 24


@dataclass
class ProviderHealthRow:
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


@dataclass
class CheckRunResult:
    checked: int = 0
    statuses: dict[str, int] = field(default_factory=dict)
    duration_ms: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    failures: list[dict] = field(default_factory=list)


def health_status_for(error_code: str | None, ok: bool) -> HealthStatus:
    """Map a probe outcome onto the stored health status (same rules as M2/M4)."""
    if ok:
        return HealthStatus.HEALTHY
    if error_code == "provider_rate_limited":
        return HealthStatus.RATE_LIMITED
    if error_code in {"provider_unauthorized", "provider_forbidden", "provider_model_not_found"}:
        return HealthStatus.DOWN
    if error_code in {"credential_missing", "provider_base_url_missing"}:
        return HealthStatus.UNKNOWN
    return HealthStatus.DEGRADED


class HealthAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- reads ---------------------------------------------------------------
    async def overview(self, *, provider_id: uuid.UUID | None = None) -> list[ProviderHealthRow]:
        window_start = datetime.now(UTC) - timedelta(hours=OVERVIEW_WINDOW_HOURS)
        statement = select(Provider).order_by(Provider.priority.asc(), Provider.name.asc())
        if provider_id is not None:
            statement = statement.where(Provider.id == provider_id)
        providers = (await self.session.execute(statement)).scalars().all()

        rows: list[ProviderHealthRow] = []
        for provider in providers:
            latest = (
                (
                    await self.session.execute(
                        select(HealthCheck)
                        .where(HealthCheck.provider_id == provider.id)
                        .order_by(HealthCheck.checked_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )

            usage = (
                await self.session.execute(
                    select(
                        func.count(UsageRecord.id),
                        func.coalesce(
                            func.sum(case((UsageRecord.error_code.is_not(None), 1), else_=0)),
                            0,
                        ),
                        func.avg(UsageRecord.latency_ms),
                    ).where(
                        UsageRecord.provider_id == provider.id,
                        UsageRecord.created_at >= window_start,
                    )
                )
            ).one()
            requests, errors, avg_latency = int(usage[0] or 0), int(usage[1] or 0), usage[2]

            checks = (
                await self.session.execute(
                    select(
                        func.count(HealthCheck.id),
                        func.coalesce(
                            func.sum(
                                case((HealthCheck.status == HealthStatus.HEALTHY, 1), else_=0)
                            ),
                            0,
                        ),
                    ).where(
                        HealthCheck.provider_id == provider.id,
                        HealthCheck.checked_at >= window_start,
                    )
                )
            ).one()
            total_checks, healthy_checks = int(checks[0] or 0), int(checks[1] or 0)

            credential_count = int(
                (
                    await self.session.execute(
                        select(func.count(ProviderCredential.id)).where(
                            ProviderCredential.provider_id == provider.id
                        )
                    )
                ).scalar_one()
            )
            model_count = int(
                (
                    await self.session.execute(
                        select(func.count(Model.id)).where(Model.provider_id == provider.id)
                    )
                ).scalar_one()
            )

            status = HealthStatus(latest.status) if latest is not None else HealthStatus.UNKNOWN
            rows.append(
                ProviderHealthRow(
                    provider_id=provider.id,
                    name=provider.name,
                    slug=provider.slug,
                    enabled=provider.enabled,
                    status=status,
                    last_checked_at=latest.checked_at if latest else None,
                    latency_ms=latest.latency_ms if latest else None,
                    error_code=latest.error_code if latest else None,
                    requests=requests,
                    errors=errors,
                    error_rate=round(errors / requests, 4) if requests else 0.0,
                    avg_latency_ms=int(avg_latency) if avg_latency is not None else None,
                    uptime_percent=(
                        round(healthy_checks / total_checks * 100, 2) if total_checks else None
                    ),
                    credential_count=credential_count,
                    model_count=model_count,
                )
            )
        return rows

    async def history(
        self,
        *,
        provider_id: uuid.UUID | None = None,
        target_type: str | None = None,
        limit: int = 50,
    ) -> list[HealthCheck]:
        statement = select(HealthCheck).order_by(HealthCheck.checked_at.desc()).limit(limit)
        if provider_id is not None:
            statement = statement.where(HealthCheck.provider_id == provider_id)
        if target_type is not None:
            statement = statement.where(HealthCheck.target_type == target_type)
        return list((await self.session.execute(statement)).scalars().all())

    # -- checks --------------------------------------------------------------
    async def check_provider(self, provider: Provider) -> dict:
        """Probe one provider through its first credential and store the observation."""
        credential = (
            (
                await self.session.execute(
                    select(ProviderCredential)
                    .where(
                        ProviderCredential.provider_id == provider.id,
                        ProviderCredential.status != CredentialStatus.REVOKED,
                    )
                    .order_by(ProviderCredential.created_at.asc())
                )
            )
            .scalars()
            .first()
        )

        if credential is None:
            observation = await record_health_check(
                self.session,
                HealthTarget.provider(provider.id),
                status=HealthStatus.UNKNOWN,
                error_code="credential_missing",
            )
            provider.health_status = HealthStatus.UNKNOWN.value
            await self.session.flush()
            return {
                "provider_id": str(provider.id),
                "status": observation.status.value,
                "error_code": "credential_missing",
            }

        try:
            secret = decrypt_secret(credential.encrypted_secret)
        except EncryptionError:
            await record_health_check(
                self.session,
                HealthTarget.provider(provider.id),
                status=HealthStatus.DOWN,
                error_code="credential_decryption_failed",
            )
            provider.health_status = HealthStatus.DOWN.value
            await self.session.flush()
            return {
                "provider_id": str(provider.id),
                "status": HealthStatus.DOWN.value,
                "error_code": "credential_decryption_failed",
            }

        adapter = build_adapter(
            kind=provider.kind,
            base_url=provider.base_url,
            secret=secret,
            timeout_ms=provider.timeout_ms,
        )
        result = await adapter.probe()
        status = health_status_for(result.error_code, result.ok)

        await record_health_check(
            self.session,
            HealthTarget.provider(provider.id),
            status=status,
            latency_ms=result.latency_ms,
            status_code=result.status_code,
            error_code=result.error_code,
        )
        await record_health_check(
            self.session,
            HealthTarget.credential(credential.id, provider_id=provider.id),
            status=status,
            latency_ms=result.latency_ms,
            status_code=result.status_code,
            error_code=result.error_code,
        )
        credential.status = CredentialStatus.ACTIVE if result.ok else credential.status
        credential.last_verified_at = datetime.now(UTC)
        credential.last_error_code = result.error_code
        provider.health_status = status.value
        await self.session.flush()
        return {
            "provider_id": str(provider.id),
            "status": status.value,
            "latency_ms": result.latency_ms,
            "error_code": result.error_code,
        }

    async def run_checks(
        self,
        *,
        actor: AdminUser | None = None,
        provider_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> CheckRunResult:
        statement = (
            select(Provider).where(Provider.enabled.is_(True)).order_by(Provider.priority.asc())
        )
        if provider_id is not None:
            statement = select(Provider).where(Provider.id == provider_id)
        providers = (await self.session.execute(statement)).scalars().all()

        started = datetime.now(UTC)
        outcome = CheckRunResult(started_at=started)
        for provider in providers:
            try:
                result = await self.check_provider(provider)
            except Exception as exc:  # pragma: no cover - a probe may fail in any way
                logger.warning(
                    "health_check_failed", extra={"provider": str(provider.id), "error": str(exc)}
                )
                result = {"provider_id": str(provider.id), "status": "down", "error_code": None}
            outcome.checked += 1
            status = str(result.get("status", "unknown"))
            outcome.statuses[status] = outcome.statuses.get(status, 0) + 1
            if status not in {"healthy"}:
                outcome.failures.append(result)

        outcome.duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        if actor is not None:
            await AuditService(self.session).record(
                AuditAction.HEALTH_CHECKS_RUN,
                actor=actor,
                entity_type="provider",
                entity_id=str(provider_id) if provider_id else None,
                diff={
                    "checked": outcome.checked,
                    "statuses": outcome.statuses,
                    "duration_ms": outcome.duration_ms,
                },
                ip_address=ip_address,
                user_agent=user_agent,
            )
        return outcome


# --------------------------------------------------------------------------- #
# Scheduler
# --------------------------------------------------------------------------- #
class HealthScheduler:
    """Periodic batch checks, disabled unless explicitly enabled.

    A timer that silently probes every upstream on every deployment would be a
    surprise (and a cost); ``XEREX_HEALTH_SCHEDULER_ENABLED`` turns it on, and the
    interval comes from ``XEREX_HEALTH_CHECK_INTERVAL_SECONDS``.
    """

    def __init__(self, interval_seconds: int | None = None) -> None:
        self.interval_seconds = interval_seconds or settings.health_check_interval_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.runs = 0
        self.last_run_at: datetime | None = None

    @property
    def enabled(self) -> bool:
        return settings.health_scheduler_enabled and self.interval_seconds > 0

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._loop())
        logger.info("health_scheduler_started", extra={"interval": self.interval_seconds})

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        await self._task
        self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception:  # pragma: no cover - never kill the loop
                logger.warning("health_scheduler_run_failed", exc_info=True)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue

    async def run_once(self) -> CheckRunResult:
        async with session_scope() as session:
            outcome = await HealthAdminService(session).run_checks()
        self.runs += 1
        self.last_run_at = datetime.now(UTC)
        return outcome


#: One scheduler per process; ``app.main`` starts and stops it with the lifespan.
scheduler = HealthScheduler()


__all__ = [
    "CheckRunResult",
    "HealthAdminService",
    "HealthScheduler",
    "ProviderHealthRow",
    "health_status_for",
    "scheduler",
]
