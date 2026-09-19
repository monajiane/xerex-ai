"""Usage analytics, request logs and exports («مصرف» and «گزارش‌ها») — M6.

The API speaks ISO-8601 dates: the Persian panel converts Jalali input at the edge, and
the backend stays free of calendar conversion. Every number here is computed from the
stored attempt rows — nothing is estimated, and an empty window returns zeros with an
explicit empty state rather than fabricated activity.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from app.api.deps import SessionDep
from app.auth.dependencies import require_roles
from app.core.errors import NotFoundError
from app.models.enums import AdminRole, ClientRequestState
from app.models.identity import AdminUser
from app.schemas.common import Page
from app.schemas.usage import (
    RequestAttemptRead,
    RequestLogDetail,
    RequestLogEntry,
    UsageBreakdown,
    UsageFilter,
    UsageSummary,
)
from app.services.usage import UsageService

router = APIRouter(prefix="/usage", tags=["usage"])

READ_ROLES = (AdminRole.OWNER, AdminRole.ADMIN, AdminRole.OPERATOR, AdminRole.VIEWER)


def _filters(
    date_from: Annotated[date | None, Query(description="Inclusive start date (ISO-8601).")] = None,
    date_to: Annotated[date | None, Query(description="Inclusive end date (ISO-8601).")] = None,
    provider_id: Annotated[uuid.UUID | None, Query()] = None,
    model_id: Annotated[uuid.UUID | None, Query()] = None,
    api_key_id: Annotated[uuid.UUID | None, Query()] = None,
) -> UsageFilter:
    return UsageFilter(
        date_from=date_from,
        date_to=date_to,
        provider_id=provider_id,
        model_id=model_id,
        api_key_id=api_key_id,
    )


FiltersDep = Annotated[UsageFilter, Depends(_filters)]


@router.get("/summary", response_model=UsageSummary)
async def usage_summary(
    session: SessionDep,
    filters: FiltersDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    interval: Annotated[Literal["hour", "day", "week", "month"], Query()] = "day",
) -> UsageSummary:
    """Totals plus a time series for the selected window (default: last 7 days)."""
    return await UsageService(session).summary(filters, interval=interval)


@router.get("/breakdown", response_model=UsageBreakdown)
async def usage_breakdown(
    session: SessionDep,
    filters: FiltersDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    dimension: Annotated[
        Literal["provider", "model", "api_key"], Query(description="Grouping dimension.")
    ] = "provider",
) -> UsageBreakdown:
    rows = await UsageService(session).breakdown(filters, dimension=dimension)
    return UsageBreakdown(dimension=dimension, items=[row.__dict__ for row in rows])


@router.get("/requests", response_model=Page[RequestLogEntry])
async def request_logs(
    session: SessionDep,
    filters: FiltersDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    state: Annotated[ClientRequestState | None, Query()] = None,
    error_code: Annotated[str | None, Query(max_length=80)] = None,
    search: Annotated[str | None, Query(max_length=160)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Page[RequestLogEntry]:
    """One row per client request: outcome, attempts, tokens, latency."""
    result = await UsageService(session).requests(
        filters,
        state=state,
        error_code=error_code,
        search=search,
        offset=(page - 1) * page_size,
        limit=page_size,
    )
    return Page(items=result.items, total=result.total, page=page, page_size=page_size)


@router.get("/requests/{request_id}", response_model=RequestLogDetail)
async def request_detail(
    request_id: str,
    session: SessionDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
) -> RequestLogDetail:
    """The request plus every upstream attempt it took — what failover actually did."""
    detail = await UsageService(session).request_detail(request_id)
    if detail is None:
        raise NotFoundError("The request was not found.", code="request_not_found")

    record = detail.request
    final = next(
        (attempt for attempt in detail.attempts if attempt.is_final),
        detail.attempts[-1] if detail.attempts else None,
    )
    entry = RequestLogEntry(
        id=record.id,
        request_id=record.request_id,
        api_key_name=None,
        provider_name=detail.provider_names.get(final.provider_id)
        if final and final.provider_id
        else None,
        model_name=detail.model_names.get(final.model_id) if final and final.model_id else None,
        status_code=int(record.final_status_code or 0),
        error_code=record.final_error_code,
        latency_ms=int(record.latency_ms or 0),
        total_tokens=int(record.total_tokens or 0),
        streaming=bool(record.streaming),
        state=record.state.value if hasattr(record.state, "value") else str(record.state),
        attempt_count=int(record.attempt_count or 0),
        created_at=record.started_at,
    )
    return RequestLogDetail(
        request=entry,
        attempts=[
            RequestAttemptRead(
                id=attempt.id,
                attempt_number=attempt.attempt_number,
                is_final=attempt.is_final,
                retryable=attempt.retryable,
                provider_name=detail.provider_names.get(attempt.provider_id),
                model_name=detail.model_names.get(attempt.model_id),
                credential_label=detail.credential_labels.get(attempt.credential_id),
                endpoint_path=detail.endpoint_paths.get(attempt.endpoint_id),
                status_code=attempt.status_code,
                error_code=attempt.error_code,
                latency_ms=attempt.latency_ms,
                input_tokens=attempt.input_tokens,
                output_tokens=attempt.output_tokens,
                total_tokens=attempt.total_tokens,
                cost=float(attempt.cost or 0),
                streaming=attempt.streaming,
                created_at=attempt.created_at,
            )
            for attempt in detail.attempts
        ],
    )


@router.get("/export")
async def export_usage(
    session: SessionDep,
    filters: FiltersDep,
    _: AdminUser = Depends(require_roles(*READ_ROLES)),
    format: Annotated[Literal["csv", "json"], Query(description="Export format.")] = "csv",
    default_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> Response:
    """One row per attempt. CSV is BOM-prefixed so Excel reads Persian labels correctly."""
    service = UsageService(session)
    rows = await service.export_rows(filters, default_days=default_days)
    stamp = date.today().isoformat()

    if format == "json":
        return Response(
            content=service.to_json(rows),
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="xerex-usage-{stamp}.json"',
                "X-Row-Count": str(len(rows)),
            },
        )
    return Response(
        content=service.to_csv(rows),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="xerex-usage-{stamp}.csv"',
            "X-Row-Count": str(len(rows)),
        },
    )


@router.post("/rollups/rebuild")
async def rebuild_rollups(
    session: SessionDep,
    _: AdminUser = Depends(require_roles(AdminRole.OWNER, AdminRole.ADMIN)),
    day: Annotated[date | None, Query(description="Day to recompute (default: today).")] = None,
) -> dict[str, int]:
    """Recompute the daily rollup for one day from the stored attempts."""
    written = await UsageService(session).rebuild_rollups(day=day)
    return {"rows": written}
