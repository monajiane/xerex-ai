"""Usage and request-log contracts (frozen shape for milestone M6).

Aggregated values are always Latin digits and ISO-8601 timestamps; the Persian
admin panel only converts them at render time.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from app.schemas.common import ApiModel


class UsageFilter(ApiModel):
    date_from: date | None = None
    date_to: date | None = None
    provider_id: uuid.UUID | None = None
    model_id: uuid.UUID | None = None
    api_key_id: uuid.UUID | None = None


class UsagePoint(ApiModel):
    bucket: datetime
    requests: int
    tokens: int
    cost: float
    error_rate: float
    p95_latency_ms: int


class UsageSeries(ApiModel):
    interval: str = "day"
    points: list[UsagePoint] = []


class UsageTotals(ApiModel):
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    p95_latency_ms: int = 0
    error_rate: float = 0.0


class UsageSummary(ApiModel):
    totals: UsageTotals
    series: UsageSeries
    generated_at: datetime


class RequestLogEntry(ApiModel):
    id: uuid.UUID
    request_id: str
    api_key_name: str | None = None
    provider_name: str | None = None
    model_name: str | None = None
    status_code: int
    error_code: str | None = None
    latency_ms: int
    total_tokens: int
    streaming: bool
    created_at: datetime
