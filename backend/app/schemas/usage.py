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
    """One interval of the usage series.

    The latency here is an **average** for that interval: a per-bucket percentile is not
    portable across PostgreSQL and SQLite, and the milestone prefers an honest average
    over a number whose name promises more than it computes. The window-wide p95 lives
    in :class:`UsageTotals`, where it is computed from the ordered rows.
    """

    bucket: datetime
    requests: int
    tokens: int
    cost: float
    error_rate: float
    avg_latency_ms: int


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
    avg_latency_ms: int | None = None
    error_rate: float = 0.0
    error_count: int = 0


class UsageSummary(ApiModel):
    totals: UsageTotals
    series: UsageSeries
    generated_at: datetime
    range_start: datetime
    range_end: datetime


class UsageBreakdownRow(ApiModel):
    """One line of the «مصرف» breakdown: per provider, model or API key."""

    key: str
    label: str
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    errors: int = 0
    avg_latency_ms: int | None = None
    error_rate: float = 0.0


class UsageBreakdown(ApiModel):
    dimension: str
    items: list[UsageBreakdownRow] = []


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
    #: ``pending`` | ``succeeded`` | ``failed`` — the final state of the client request.
    state: str = "succeeded"
    #: How many upstream attempts it took (failover visible at a glance).
    attempt_count: int = 0
    created_at: datetime


class RequestAttemptRead(ApiModel):
    """One upstream attempt inside a logged request (the failover story)."""

    id: uuid.UUID
    attempt_number: int
    is_final: bool
    retryable: bool
    provider_name: str | None = None
    model_name: str | None = None
    credential_label: str | None = None
    endpoint_path: str | None = None
    status_code: int
    error_code: str | None = None
    latency_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    streaming: bool = False
    created_at: datetime


class RequestLogDetail(ApiModel):
    request: RequestLogEntry
    attempts: list[RequestAttemptRead] = []
