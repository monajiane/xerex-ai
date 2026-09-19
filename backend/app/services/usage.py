"""Usage analytics, request logs and exports (M6).

Design rules:

* **Aggregates come from the attempt rows.** One client request can fan out into
  several attempts, so tokens, cost and latency are summed per attempt — that is what
  the provider actually did, and per-credential accountability depends on it.
* **Time ranges are inclusive and explicit.** The API speaks ISO-8601 (Gregorian)
  because it is a technical contract; the Persian panel converts Jalali dates at the
  edge, which keeps the backend free of calendar conversion.
* **Exports stream stored rows**, they do not re-aggregate in the client, and CSV is
  written with a UTF-8 BOM so Excel opens Persian text correctly.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ClientRequestState
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.models.usage import ApiKey, ClientRequest, UsageDailyRollup, UsageRecord
from app.schemas.usage import (
    RequestLogEntry,
    UsageFilter,
    UsagePoint,
    UsageSeries,
    UsageSummary,
    UsageTotals,
)

Interval = Literal["hour", "day", "week", "month"]

#: Hard cap on exported rows: an export must not be able to exhaust memory.
EXPORT_ROW_LIMIT = 50_000


def _as_utc_datetime(value: Any) -> datetime:
    """Normalise a backend-specific bucket value to an aware UTC datetime.

    PostgreSQL returns ``datetime`` (sometimes naive), SQLite returns a string such as
    ``2026-09-19T00:00:00`` or ``2026-09-14``. The API contract is always the same.
    """
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str):
        moment = datetime.fromisoformat(value)
    elif isinstance(value, date):
        moment = datetime.combine(value, time.min)
    else:  # pragma: no cover - defensive: an unexpected backend type
        raise TypeError(f"unsupported bucket value: {value!r}")
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


def _final_attempt_subquery() -> Select:
    """The successful (or last) attempt of a request, with its provider/model labels.

    A request log line shows *where the request was finally served*; the attempt rows
    remain the source of truth for every intermediate failover, which is what the
    detail view lists.
    """
    return (
        select(
            UsageRecord.client_request_id.label("client_request_id"),
            UsageRecord.provider_id.label("provider_id"),
            UsageRecord.model_id.label("model_id"),
            Provider.name.label("provider_name"),
            Model.name.label("model_name"),
        )
        .join(Provider, Provider.id == UsageRecord.provider_id, isouter=True)
        .join(Model, Model.id == UsageRecord.model_id, isouter=True)
        .where(UsageRecord.is_final.is_(True))
        .subquery()
    )


final_attempt = _final_attempt_subquery()

#: Bucket starts are normalised to a Monday for ``week`` on both backends.
SQLITE_BUCKETS: dict[str, str] = {
    "hour": "%Y-%m-%dT%H:00:00",
    "day": "%Y-%m-%dT00:00:00",
    "week": None,  # special-cased: the Monday of the week
    "month": "%Y-%m-01T00:00:00",
}

POSTGRES_BUCKETS: dict[str, str] = {
    "hour": "hour",
    "day": "day",
    "week": "week",
    "month": "month",
}


def _bucket_expression(interval: Interval, dialect: str) -> Any:
    """Portable time bucket.

    PostgreSQL gets ``date_trunc``; SQLite (used by the test suite) gets the equivalent
    ``strftime``/``date`` expression. Keeping both explicit beats silently degrading
    every interval to a day when the panel asks for hours.
    """
    column = UsageRecord.created_at
    if dialect == "postgresql":
        return func.date_trunc(POSTGRES_BUCKETS[interval], column).label("bucket")
    if interval == "week":
        # ``weekday 0`` moves to the next Sunday, six days back is that week's Monday.
        return func.date(column, "weekday 0", "-6 days").label("bucket")
    return func.strftime(SQLITE_BUCKETS[interval], column).label("bucket")


@dataclass
class RequestDetail:
    """A logged request with its attempts and the labels resolved in bulk."""

    request: ClientRequest
    attempts: list[UsageRecord]
    provider_names: dict[Any, str] = field(default_factory=dict)
    model_names: dict[Any, str] = field(default_factory=dict)
    endpoint_paths: dict[Any, str] = field(default_factory=dict)
    credential_labels: dict[Any, str] = field(default_factory=dict)


@dataclass
class BreakdownRow:
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


@dataclass
class RequestLogPage:
    items: list[RequestLogEntry] = field(default_factory=list)
    total: int = 0


def resolve_window(
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    default_days: int = 7,
) -> tuple[datetime, datetime]:
    """Turn the optional inclusive date range into a concrete UTC window."""
    end_date = date_to or datetime.now(UTC).date()
    start_date = date_from or (end_date - timedelta(days=default_days - 1))
    start = datetime.combine(start_date, time.min, tzinfo=UTC)
    end = datetime.combine(end_date, time.max, tzinfo=UTC)
    if start > end:
        start, end = end, start
    return start, end


class UsageService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- summary -------------------------------------------------------------
    async def summary(
        self, filters: UsageFilter, *, interval: Interval = "day", default_days: int = 7
    ) -> UsageSummary:
        start, end = resolve_window(
            date_from=filters.date_from, date_to=filters.date_to, default_days=default_days
        )
        totals = await self.totals(filters, default_days=default_days)
        series = await self.series(filters, interval=interval, start=start, end=end)
        return UsageSummary(
            totals=totals,
            series=series,
            generated_at=datetime.now(UTC),
            range_start=start,
            range_end=end,
        )

    async def totals(self, filters: UsageFilter, *, default_days: int = 7) -> UsageTotals:
        start, end = resolve_window(
            date_from=filters.date_from, date_to=filters.date_to, default_days=default_days
        )
        subquery = self._base(filters, start=start, end=end).subquery()
        row = (
            await self.session.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(subquery.c.input_tokens), 0),
                    func.coalesce(func.sum(subquery.c.output_tokens), 0),
                    func.coalesce(func.sum(subquery.c.total_tokens), 0),
                    func.coalesce(func.sum(subquery.c.cost), 0),
                    func.avg(subquery.c.latency_ms),
                    func.coalesce(
                        func.sum(case((subquery.c.error_code.is_not(None), 1), else_=0)), 0
                    ),
                ).select_from(subquery)
            )
        ).one()
        requests, input_tokens, output_tokens, total_tokens, cost, avg_latency, errors = row
        requests = int(requests or 0)
        errors = int(errors or 0)
        return UsageTotals(
            requests=requests,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            total_tokens=int(total_tokens or 0),
            cost=float(cost or 0),
            p95_latency_ms=await self._p95(filters, start=start, end=end),
            error_rate=round(errors / requests, 4) if requests else 0.0,
            avg_latency_ms=int(avg_latency) if avg_latency is not None else None,
            error_count=errors,
        )

    async def _p95(self, filters: UsageFilter, *, start: datetime, end: datetime) -> int:
        """95th percentile latency, computed on the stored attempts.

        SQLite has no ``percentile`` aggregate, so the value is taken from the ordered
        rows with an offset — the same definition on every supported database, and
        honest about an empty window (``0``).
        """
        statement = (
            self._base(filters, start=start, end=end)
            .with_only_columns(UsageRecord.latency_ms)
            .where(UsageRecord.latency_ms > 0)
            .order_by(UsageRecord.latency_ms.asc())
        )
        rows = (await self.session.execute(statement)).scalars().all()
        if not rows:
            return 0
        index = max(int(round(0.95 * len(rows))) - 1, 0)
        return int(rows[min(index, len(rows) - 1)])

    async def series(
        self,
        filters: UsageFilter,
        *,
        interval: Interval = "day",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> UsageSeries:
        start, end = (
            (start, end)
            if start and end
            else resolve_window(date_from=filters.date_from, date_to=filters.date_to)
        )
        dialect = self.session.sync_session.get_bind().dialect.name
        statement = (
            self._base(filters, start=start, end=end)
            .with_only_columns(
                _bucket_expression(interval, dialect),
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                func.coalesce(func.sum(UsageRecord.cost), 0),
                func.avg(UsageRecord.latency_ms),
                func.coalesce(func.sum(case((UsageRecord.error_code.is_not(None), 1), else_=0)), 0),
            )
            .group_by("bucket")
            .order_by("bucket")
        )
        rows = (await self.session.execute(statement)).all()
        points: list[UsagePoint] = []
        for bucket_value, requests, tokens, cost, avg_latency, errors in rows:
            requests = int(requests or 0)
            bucket = _as_utc_datetime(bucket_value)
            points.append(
                UsagePoint(
                    bucket=bucket,
                    requests=requests,
                    tokens=int(tokens or 0),
                    cost=float(cost or 0),
                    error_rate=round(int(errors or 0) / requests, 4) if requests else 0.0,
                    avg_latency_ms=int(avg_latency or 0),
                )
            )
        return UsageSeries(interval=interval, points=points)

    # -- breakdown -----------------------------------------------------------
    async def breakdown(
        self,
        filters: UsageFilter,
        *,
        dimension: Literal["provider", "model", "api_key"] = "provider",
        default_days: int = 7,
    ) -> list[BreakdownRow]:
        start, end = resolve_window(
            date_from=filters.date_from, date_to=filters.date_to, default_days=default_days
        )
        statement = self._base(filters, start=start, end=end)
        if dimension == "provider":
            statement = statement.join(
                Provider, Provider.id == UsageRecord.provider_id, isouter=True
            )
            key_column = func.coalesce(Provider.name, "—")
            id_column = UsageRecord.provider_id
        elif dimension == "model":
            statement = statement.join(Model, Model.id == UsageRecord.model_id, isouter=True)
            key_column = func.coalesce(Model.name, "—")
            id_column = UsageRecord.model_id
        else:
            statement = statement.join(ApiKey, ApiKey.id == UsageRecord.api_key_id, isouter=True)
            key_column = func.coalesce(ApiKey.name, "—")
            id_column = UsageRecord.api_key_id

        rows = (
            await self.session.execute(
                statement.with_only_columns(
                    id_column,
                    key_column,
                    func.count(UsageRecord.id),
                    func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                    func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                    func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                    func.coalesce(func.sum(UsageRecord.cost), 0),
                    func.avg(UsageRecord.latency_ms),
                    func.coalesce(
                        func.sum(case((UsageRecord.error_code.is_not(None), 1), else_=0)), 0
                    ),
                )
                .group_by(id_column, key_column)
                .order_by(func.count(UsageRecord.id).desc())
            )
        ).all()

        results: list[BreakdownRow] = []
        for (
            row_id,
            label,
            requests,
            input_tokens,
            output_tokens,
            total_tokens,
            cost,
            avg_latency,
            errors,
        ) in rows:
            requests = int(requests or 0)
            errors = int(errors or 0)
            results.append(
                BreakdownRow(
                    key=str(row_id) if row_id else "—",
                    label=str(label),
                    requests=requests,
                    input_tokens=int(input_tokens or 0),
                    output_tokens=int(output_tokens or 0),
                    total_tokens=int(total_tokens or 0),
                    cost=float(cost or 0),
                    errors=errors,
                    avg_latency_ms=int(avg_latency) if avg_latency is not None else None,
                    error_rate=round(errors / requests, 4) if requests else 0.0,
                )
            )
        return results

    # -- request logs --------------------------------------------------------
    async def requests(
        self,
        filters: UsageFilter,
        *,
        state: ClientRequestState | None = None,
        error_code: str | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 50,
        default_days: int = 7,
    ) -> RequestLogPage:
        start, end = resolve_window(
            date_from=filters.date_from, date_to=filters.date_to, default_days=default_days
        )
        statement = self._requests_base(
            filters, start=start, end=end, state=state, error_code=error_code, search=search
        )
        counter = select(func.count()).select_from(statement.subquery())
        total = int((await self.session.execute(counter)).scalar_one())

        rows = (
            await self.session.execute(
                statement.with_only_columns(
                    ClientRequest.id,
                    ClientRequest.request_id,
                    ApiKey.name,
                    final_attempt.c.provider_name,
                    final_attempt.c.model_name,
                    ClientRequest.final_status_code,
                    ClientRequest.final_error_code,
                    ClientRequest.latency_ms,
                    ClientRequest.total_tokens,
                    ClientRequest.streaming,
                    ClientRequest.state,
                    ClientRequest.attempt_count,
                    ClientRequest.started_at,
                )
                .order_by(ClientRequest.started_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).all()

        items = [
            RequestLogEntry(
                id=row[0],
                request_id=row[1],
                api_key_name=row[2],
                provider_name=row[3],
                model_name=row[4],
                status_code=int(row[5] or 0),
                error_code=row[6],
                latency_ms=int(row[7] or 0),
                total_tokens=int(row[8] or 0),
                streaming=bool(row[9]),
                state=row[10],
                attempt_count=int(row[11] or 0),
                created_at=row[12],
            )
            for row in rows
        ]
        return RequestLogPage(items=items, total=total)

    async def request_detail(self, request_id: str) -> RequestDetail | None:
        """One client request, its attempts and the labels they should be shown with.

        Labels are resolved with **one query per entity type** (`IN (...)`) rather than
        per attempt: a request that failed over eight times must not cost eight round
        trips to render one drawer.
        """
        record = (
            (
                await self.session.execute(
                    select(ClientRequest).where(ClientRequest.request_id == request_id)
                )
            )
            .scalars()
            .first()
        )
        if record is None:
            return None
        attempts = list(
            (
                await self.session.execute(
                    select(UsageRecord)
                    .where(UsageRecord.client_request_id == record.id)
                    .order_by(UsageRecord.attempt_number.asc())
                )
            )
            .scalars()
            .all()
        )

        provider_names: dict[Any, str] = {}
        model_names: dict[Any, str] = {}
        endpoint_paths: dict[Any, str] = {}
        credential_labels: dict[Any, str] = {}

        provider_ids = {attempt.provider_id for attempt in attempts if attempt.provider_id}
        if provider_ids:
            rows = await self.session.execute(
                select(Provider.id, Provider.name).where(Provider.id.in_(provider_ids))
            )
            provider_names = {row[0]: row[1] for row in rows}
        model_ids = {attempt.model_id for attempt in attempts if attempt.model_id}
        if model_ids:
            rows = await self.session.execute(
                select(Model.id, Model.name).where(Model.id.in_(model_ids))
            )
            model_names = {row[0]: row[1] for row in rows}
        endpoint_ids = {attempt.endpoint_id for attempt in attempts if attempt.endpoint_id}
        if endpoint_ids:
            rows = await self.session.execute(
                select(ModelEndpoint.id, ModelEndpoint.path).where(
                    ModelEndpoint.id.in_(endpoint_ids)
                )
            )
            endpoint_paths = {row[0]: row[1] for row in rows}
        credential_ids = {attempt.credential_id for attempt in attempts if attempt.credential_id}
        if credential_ids:
            rows = await self.session.execute(
                select(ProviderCredential.id, ProviderCredential.label).where(
                    ProviderCredential.id.in_(credential_ids)
                )
            )
            credential_labels = {row[0]: row[1] for row in rows}

        return RequestDetail(
            request=record,
            attempts=attempts,
            provider_names=provider_names,
            model_names=model_names,
            endpoint_paths=endpoint_paths,
            credential_labels=credential_labels,
        )

    # -- exports -------------------------------------------------------------
    async def export_rows(
        self, filters: UsageFilter, *, default_days: int = 30
    ) -> list[dict[str, Any]]:
        """Flat rows for CSV/JSON export: one row per attempt, with its labels."""
        start, end = resolve_window(
            date_from=filters.date_from, date_to=filters.date_to, default_days=default_days
        )
        statement = (
            self._base(filters, start=start, end=end)
            .with_only_columns(
                UsageRecord.request_id,
                UsageRecord.attempt_number,
                func.coalesce(ApiKey.name, "—"),
                func.coalesce(Provider.name, "—"),
                func.coalesce(Model.name, "—"),
                UsageRecord.status_code,
                UsageRecord.error_code,
                UsageRecord.input_tokens,
                UsageRecord.output_tokens,
                UsageRecord.total_tokens,
                UsageRecord.cost,
                UsageRecord.latency_ms,
                UsageRecord.streaming,
                UsageRecord.created_at,
            )
            .join(ApiKey, ApiKey.id == UsageRecord.api_key_id, isouter=True)
            .join(Provider, Provider.id == UsageRecord.provider_id, isouter=True)
            .join(Model, Model.id == UsageRecord.model_id, isouter=True)
            .order_by(UsageRecord.created_at.desc())
            .limit(EXPORT_ROW_LIMIT)
        )
        rows = (await self.session.execute(statement)).all()
        return [
            {
                "request_id": row[0],
                "attempt_number": int(row[1] or 1),
                "api_key_name": row[2],
                "provider_name": row[3],
                "model_name": row[4],
                "status_code": int(row[5] or 0),
                "error_code": row[6],
                "input_tokens": int(row[7] or 0),
                "output_tokens": int(row[8] or 0),
                "total_tokens": int(row[9] or 0),
                "cost_usd": float(row[10] or 0),
                "latency_ms": int(row[11] or 0),
                "streaming": bool(row[12]),
                "created_at": row[13].isoformat() if row[13] else None,
            }
            for row in rows
        ]

    @staticmethod
    def to_csv(rows: list[dict[str, Any]]) -> str:
        """CSV with a UTF-8 BOM so Excel renders Persian labels instead of mojibake."""
        if not rows:
            return "\ufeff"
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        return "\ufeff" + buffer.getvalue()

    @staticmethod
    def to_json(rows: list[dict[str, Any]]) -> str:
        return json.dumps(rows, ensure_ascii=False, indent=2, default=str)

    # -- rollups -------------------------------------------------------------
    async def rebuild_rollups(self, *, day: date | None = None) -> int:
        """Recompute the daily rollup for one day (used by the CLI/seed and M6 dashboards)."""
        target = day or datetime.now(UTC).date()
        start = datetime.combine(target, time.min, tzinfo=UTC)
        end = datetime.combine(target, time.max, tzinfo=UTC)

        rows = (
            await self.session.execute(
                select(
                    UsageRecord.provider_id,
                    UsageRecord.model_id,
                    UsageRecord.api_key_id,
                    func.count(UsageRecord.id),
                    func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                    func.coalesce(func.sum(UsageRecord.cost), 0),
                    func.avg(UsageRecord.latency_ms),
                    func.coalesce(
                        func.sum(case((UsageRecord.error_code.is_not(None), 1), else_=0)), 0
                    ),
                )
                .where(UsageRecord.created_at >= start, UsageRecord.created_at <= end)
                .group_by(UsageRecord.provider_id, UsageRecord.model_id, UsageRecord.api_key_id)
            )
        ).all()

        existing = {
            (row.provider_id, row.model_id, row.api_key_id): row
            for row in (
                await self.session.execute(
                    select(UsageDailyRollup).where(UsageDailyRollup.day == target)
                )
            )
            .scalars()
            .all()
        }

        written = 0
        for provider_id, model_id, api_key_id, requests, tokens, cost, avg_latency, errors in rows:
            requests = int(requests or 0)
            entry = existing.get((provider_id, model_id, api_key_id))
            if entry is None:
                entry = UsageDailyRollup(
                    day=target, provider_id=provider_id, model_id=model_id, api_key_id=api_key_id
                )
                self.session.add(entry)
            entry.requests = requests
            entry.tokens = int(tokens or 0)
            entry.cost = Decimal(str(cost or 0))
            entry.p95_latency_ms = int(avg_latency or 0)
            entry.error_rate = Decimal(
                str(round(int(errors or 0) / requests, 4) if requests else 0)
            )
            written += 1
        await self.session.flush()
        return written

    # -- query builders ------------------------------------------------------
    def _base(self, filters: UsageFilter, *, start: datetime, end: datetime) -> Select:
        statement = select(UsageRecord).where(
            UsageRecord.created_at >= start, UsageRecord.created_at <= end
        )
        if filters.provider_id:
            statement = statement.where(UsageRecord.provider_id == filters.provider_id)
        if filters.model_id:
            statement = statement.where(UsageRecord.model_id == filters.model_id)
        if filters.api_key_id:
            statement = statement.where(UsageRecord.api_key_id == filters.api_key_id)
        return statement

    def _requests_base(
        self,
        filters: UsageFilter,
        *,
        start: datetime,
        end: datetime,
        state: ClientRequestState | None,
        error_code: str | None,
        search: str | None,
    ) -> Select:
        statement = (
            select(ClientRequest)
            .where(ClientRequest.started_at >= start, ClientRequest.started_at <= end)
            .join(ApiKey, ApiKey.id == ClientRequest.api_key_id, isouter=True)
            .join(
                final_attempt, final_attempt.c.client_request_id == ClientRequest.id, isouter=True
            )
        )
        if filters.api_key_id:
            statement = statement.where(ClientRequest.api_key_id == filters.api_key_id)
        if filters.provider_id:
            statement = statement.where(final_attempt.c.provider_id == filters.provider_id)
        if filters.model_id:
            statement = statement.where(final_attempt.c.model_id == filters.model_id)
        if state is not None:
            statement = statement.where(ClientRequest.state == state)
        if error_code:
            statement = statement.where(ClientRequest.final_error_code == error_code)
        if search:
            pattern = f"%{search.lower()}%"
            statement = statement.where(
                func.lower(ClientRequest.request_id).like(pattern)
                | func.lower(func.coalesce(ClientRequest.requested_model, "")).like(pattern)
            )
        return statement
