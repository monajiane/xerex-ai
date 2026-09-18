"""Dashboard aggregates.

All values are computed from real tables. Until M2–M6 have populated providers,
models, API keys and usage records, the honest result is a set of zeros plus
``has_provider_data = false``; the panel renders an explicit empty state instead
of demo data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.identity import AdminUser
from app.models.providers import Model, Provider
from app.models.usage import ApiKey, UsageRecord
from app.schemas.dashboard import DashboardSummary, MetricCard, TopModelRow

WINDOW_HOURS = 24


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def summary(self) -> DashboardSummary:
        window_start = datetime.now(UTC) - timedelta(hours=WINDOW_HOURS)

        provider_count = await self._scalar(select(func.count()).select_from(Provider))
        enabled_provider_count = await self._scalar(
            select(func.count()).select_from(Provider).where(Provider.enabled.is_(True))
        )
        model_count = await self._scalar(select(func.count()).select_from(Model))
        api_key_count = await self._scalar(
            select(func.count()).select_from(ApiKey).where(ApiKey.revoked_at.is_(None))
        )
        admin_user_count = await self._scalar(select(func.count()).select_from(AdminUser))

        usage = await self._usage_window(window_start)

        metrics = [
            MetricCard(
                key="requests", value=float(usage["requests"]), unit="requests", window="24h"
            ),
            MetricCard(key="tokens", value=float(usage["tokens"]), unit="tokens", window="24h"),
            MetricCard(key="cost", value=float(usage["cost"]), unit="currency", window="24h"),
            MetricCard(
                key="p95_latency_ms",
                value=float(usage["p95_latency_ms"]),
                unit="ms",
                window="24h",
                available=usage["requests"] > 0,
            ),
            MetricCard(
                key="error_rate",
                value=float(usage["error_rate"]),
                unit="ratio",
                window="24h",
                available=usage["requests"] > 0,
            ),
            MetricCard(
                key="active_providers",
                value=float(enabled_provider_count),
                unit="providers",
                window="now",
            ),
        ]

        return DashboardSummary(
            generated_at=datetime.now(UTC),
            window=f"{WINDOW_HOURS}h",
            metrics=metrics,
            provider_health=[],
            top_models=await self._top_models(window_start),
            counts={
                "providers": provider_count,
                "enabled_providers": enabled_provider_count,
                "models": model_count,
                "api_keys": api_key_count,
                "admin_users": admin_user_count,
            },
            has_provider_data=provider_count > 0,
            system_status="healthy",
        )

    # ------------------------------------------------------------------ #
    async def _usage_window(self, window_start: datetime) -> dict[str, float | int]:
        statement = select(
            func.count(UsageRecord.id),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.cost), 0),
            func.coalesce(
                func.sum(case((UsageRecord.status_code >= 400, 1), else_=0)),
                0,
            ),
        ).where(UsageRecord.created_at >= window_start)
        row = (await self.session.execute(statement)).one()
        requests = int(row[0] or 0)
        error_count = int(row[3] or 0)
        return {
            "requests": requests,
            "tokens": int(row[1] or 0),
            "cost": Decimal(row[2] or 0),
            "p95_latency_ms": await self._p95_latency(window_start),
            "error_rate": (error_count / requests) if requests else 0.0,
        }

    async def _p95_latency(self, window_start: datetime) -> int:
        statement = (
            select(UsageRecord.latency_ms)
            .where(UsageRecord.created_at >= window_start)
            .order_by(UsageRecord.latency_ms)
        )
        latencies = [int(value) for value in (await self.session.execute(statement)).scalars()]
        if not latencies:
            return 0
        index = min(int(len(latencies) * 0.95), len(latencies) - 1)
        return latencies[index]

    async def _top_models(self, window_start: datetime) -> list[TopModelRow]:
        statement = (
            select(
                Model.name,
                Provider.name,
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            )
            .select_from(UsageRecord)
            .join(Model, Model.id == UsageRecord.model_id)
            .join(Provider, Provider.id == UsageRecord.provider_id)
            .where(UsageRecord.created_at >= window_start)
            .group_by(Model.name, Provider.name)
            .order_by(func.count(UsageRecord.id).desc())
            .limit(5)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            TopModelRow(
                model_name=row[0], provider_name=row[1], requests=int(row[2]), tokens=int(row[3])
            )
            for row in rows
        ]

    async def _scalar(self, statement) -> int:  # noqa: ANN001 - SQLAlchemy select
        return int((await self.session.execute(statement)).scalar_one())
