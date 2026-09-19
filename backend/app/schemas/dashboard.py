"""Dashboard summary contract.

Every metric is computed from real database tables. While later milestones are
not implemented the underlying tables are empty, so the API returns real zeros
instead of fabricated demo data.
"""

from __future__ import annotations

from datetime import datetime

from app.schemas.common import ApiModel


class MetricCard(ApiModel):
    key: str
    value: float
    unit: str | None = None
    trend_percent: float | None = None
    window: str = "24h"
    available: bool = True


class ProviderHealthRow(ApiModel):
    provider_id: str
    name: str
    status: str
    latency_ms: float | None = None
    error_rate: float | None = None
    checked_at: datetime | None = None


class TopModelRow(ApiModel):
    model_name: str
    provider_name: str
    requests: int
    tokens: int


class DashboardSummary(ApiModel):
    generated_at: datetime
    window: str
    metrics: list[MetricCard]
    provider_health: list[ProviderHealthRow] = []
    top_models: list[TopModelRow] = []
    counts: dict[str, int]
    has_provider_data: bool
    system_status: str
