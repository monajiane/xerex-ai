"""Usage analytics, request logs and exports (M6).

The fixtures write attempt rows by hand so every aggregate can be checked against an
independently computed expectation: totals, error rate, p95 latency, breakdowns, CSV/JSON
exports and the per-attempt detail view.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.models.enums import AdminRole, ClientRequestState, CredentialStatus, HealthStatus
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.models.usage import ApiKey, ClientRequest, UsageRecord
from app.services.usage import resolve_window
from tests.conftest import create_user, login


async def _headers(client, session_factory) -> dict[str, str]:
    await create_user(session_factory)
    return {"Authorization": f"Bearer {await login(client)}"}


async def _fixture(session_factory) -> dict[str, uuid.UUID]:
    """One provider, credential, model, endpoint, key and request to hang usage on."""
    from app.core.crypto import encrypt_secret, key_hint

    async with session_factory() as session:
        provider = Provider(
            name="OpenAI Primary",
            slug="openai-primary",
            kind="openai",
            base_url="https://api.openai.com/v1",
            enabled=True,
            priority=1,
            weight=100,
            timeout_ms=30_000,
            max_retries=2,
            health_status=HealthStatus.HEALTHY.value,
        )
        session.add(provider)
        await session.flush()

        credential = ProviderCredential(
            provider_id=provider.id,
            label="primary",
            encrypted_secret=encrypt_secret("sk-live-abcdefghijklmnop"),
            key_hint=key_hint("sk-live-abcdefghijklmnop"),
            status=CredentialStatus.ACTIVE,
        )
        model = Model(provider_id=provider.id, name="gpt-4o-mini", enabled=True)
        session.add_all([credential, model])
        await session.flush()

        endpoint = ModelEndpoint(
            model_id=model.id,
            provider_id=provider.id,
            credential_id=credential.id,
            path="/chat/completions",
            method="POST",
            streaming_supported=True,
            enabled=True,
        )
        api_key = ApiKey(
            name="سرویس پشتیبانی",
            prefix="xrx_live_test0001",
            hash="hash-test-0001",
            scopes=["chat"],
            rate_limit_per_min=60,
            enabled=True,
        )
        session.add_all([endpoint, api_key])
        await session.flush()

        now = datetime.now(UTC)
        succeeded = ClientRequest(
            request_id="req-ok-1",
            api_key_id=api_key.id,
            requested_model="gpt-4o-mini",
            state=ClientRequestState.SUCCEEDED,
            attempt_count=1,
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            cost=0.003,
            latency_ms=250,
            final_status_code=200,
            started_at=now - timedelta(hours=2),
            completed_at=now - timedelta(hours=2),
        )
        failed = ClientRequest(
            request_id="req-bad-1",
            api_key_id=api_key.id,
            requested_model="gpt-4o-mini",
            state=ClientRequestState.FAILED,
            attempt_count=2,
            latency_ms=900,
            final_status_code=502,
            final_error_code="provider_unavailable",
            started_at=now - timedelta(hours=1),
            completed_at=now - timedelta(hours=1),
        )
        session.add_all([succeeded, failed])
        await session.flush()

        session.add_all(
            [
                UsageRecord(
                    request_id="req-ok-1",
                    client_request_id=succeeded.id,
                    attempt_number=1,
                    is_final=True,
                    api_key_id=api_key.id,
                    provider_id=provider.id,
                    credential_id=credential.id,
                    model_id=model.id,
                    endpoint_id=endpoint.id,
                    input_tokens=100,
                    output_tokens=50,
                    total_tokens=150,
                    cost=0.003,
                    latency_ms=250,
                    status_code=200,
                    created_at=now - timedelta(hours=2),
                ),
                UsageRecord(
                    request_id="req-bad-1",
                    client_request_id=failed.id,
                    attempt_number=1,
                    is_final=False,
                    retryable=True,
                    api_key_id=api_key.id,
                    provider_id=provider.id,
                    credential_id=credential.id,
                    model_id=model.id,
                    endpoint_id=endpoint.id,
                    latency_ms=800,
                    status_code=503,
                    error_code="provider_unavailable",
                    created_at=now - timedelta(hours=1),
                ),
                UsageRecord(
                    request_id="req-bad-1",
                    client_request_id=failed.id,
                    attempt_number=2,
                    is_final=True,
                    api_key_id=api_key.id,
                    provider_id=provider.id,
                    credential_id=credential.id,
                    model_id=model.id,
                    endpoint_id=endpoint.id,
                    latency_ms=100,
                    status_code=503,
                    error_code="provider_unavailable",
                    created_at=now - timedelta(hours=1),
                ),
            ]
        )
        await session.commit()
        return {
            "provider": provider.id,
            "model": model.id,
            "api_key": api_key.id,
            "credential": credential.id,
        }


# --------------------------------------------------------------------------- #
# Windowing
# --------------------------------------------------------------------------- #
def test_resolve_window_defaults_to_the_last_week_and_normalises_reversed_ranges() -> None:
    from datetime import date

    start, end = resolve_window(date_from=date(2026, 3, 10), date_to=date(2026, 3, 1))
    assert start <= end
    assert start.date() == date(2026, 3, 1)
    assert end.date() == date(2026, 3, 10)


# --------------------------------------------------------------------------- #
# Summary and breakdowns
# --------------------------------------------------------------------------- #
async def test_summary_totals_come_from_the_attempt_rows(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    response = await client.get("/api/v1/usage/summary?date_from=2000-01-01", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    totals = body["totals"]
    assert totals["requests"] == 3  # attempts, not client requests
    assert totals["input_tokens"] == 100
    assert totals["output_tokens"] == 50
    assert totals["total_tokens"] == 150
    assert totals["cost"] == pytest.approx(0.003)
    assert totals["error_count"] == 2
    assert totals["error_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert totals["avg_latency_ms"] == pytest.approx(383, abs=1)
    # p95 of [100, 250, 800] is the 800 sample
    assert totals["p95_latency_ms"] == 800
    assert body["series"]["interval"] == "day"
    assert body["range_start"] < body["range_end"]
    # The series latency is an honest average for the bucket, not a fake percentile.
    assert body["series"]["points"][0]["avg_latency_ms"] == pytest.approx(383, abs=1)
    assert "p95_latency_ms" not in body["series"]["points"][0]


async def test_summary_is_empty_and_honest_for_a_window_without_activity(
    client, session_factory
) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    response = await client.get(
        "/api/v1/usage/summary?date_from=1999-01-01&date_to=1999-01-02", headers=headers
    )
    totals = response.json()["totals"]
    assert totals["requests"] == 0
    assert totals["cost"] == 0
    assert totals["p95_latency_ms"] == 0
    assert response.json()["series"]["points"] == []


async def test_series_supports_every_interval(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    for interval in ("hour", "day", "week", "month"):
        response = await client.get(
            f"/api/v1/usage/summary?interval={interval}&date_from=2000-01-01", headers=headers
        )
        assert response.status_code == 200, response.text
        series = response.json()["series"]
        assert series["interval"] == interval
        assert series["points"], interval
        # Buckets are always normalised, aware UTC instants the panel can convert.
        for point in series["points"]:
            assert point["bucket"].endswith("Z") or "+00:00" in point["bucket"]
            assert point["requests"] > 0


async def test_breakdown_groups_by_provider_model_and_key(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    for dimension, expected in (
        ("provider", "OpenAI Primary"),
        ("model", "gpt-4o-mini"),
        ("api_key", "سرویس پشتیبانی"),
    ):
        response = await client.get(
            f"/api/v1/usage/breakdown?dimension={dimension}&date_from=2000-01-01", headers=headers
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["dimension"] == dimension
        assert len(body["items"]) == 1
        row = body["items"][0]
        assert row["label"] == expected
        assert row["requests"] == 3
        assert row["errors"] == 2
        assert row["cost"] == pytest.approx(0.003)


async def test_breakdown_can_be_filtered_by_provider(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    ids = await _fixture(session_factory)

    response = await client.get(
        f"/api/v1/usage/breakdown?dimension=model&provider_id={ids['provider']}"
        "&date_from=2000-01-01",
        headers=headers,
    )
    assert len(response.json()["items"]) == 1

    empty = await client.get(
        f"/api/v1/usage/breakdown?dimension=model&provider_id={uuid.uuid4()}&date_from=2000-01-01",
        headers=headers,
    )
    assert empty.json()["items"] == []


# --------------------------------------------------------------------------- #
# Request logs
# --------------------------------------------------------------------------- #
async def test_request_logs_list_outcomes_with_attempt_counts(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    response = await client.get("/api/v1/usage/requests?date_from=2000-01-01", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2

    by_id = {item["request_id"]: item for item in body["items"]}
    assert by_id["req-ok-1"]["state"] == "succeeded"
    assert by_id["req-ok-1"]["attempt_count"] == 1
    assert by_id["req-ok-1"]["provider_name"] == "OpenAI Primary"
    assert by_id["req-ok-1"]["model_name"] == "gpt-4o-mini"
    assert by_id["req-bad-1"]["state"] == "failed"
    assert by_id["req-bad-1"]["attempt_count"] == 2
    assert by_id["req-bad-1"]["error_code"] == "provider_unavailable"
    assert by_id["req-bad-1"]["status_code"] == 502


async def test_request_logs_filter_by_state_error_and_search(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    failed = await client.get(
        "/api/v1/usage/requests?state=failed&date_from=2000-01-01", headers=headers
    )
    assert [item["request_id"] for item in failed.json()["items"]] == ["req-bad-1"]

    by_error = await client.get(
        "/api/v1/usage/requests?error_code=provider_unavailable&date_from=2000-01-01",
        headers=headers,
    )
    assert len(by_error.json()["items"]) == 1

    searched = await client.get(
        "/api/v1/usage/requests?search=req-ok&date_from=2000-01-01", headers=headers
    )
    assert [item["request_id"] for item in searched.json()["items"]] == ["req-ok-1"]

    none = await client.get(
        "/api/v1/usage/requests?search=nothing-here&date_from=2000-01-01", headers=headers
    )
    assert none.json()["items"] == []


async def test_request_detail_lists_every_attempt(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    response = await client.get("/api/v1/usage/requests/req-bad-1", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request"]["attempt_count"] == 2
    attempts = body["attempts"]
    assert [attempt["attempt_number"] for attempt in attempts] == [1, 2]
    assert attempts[0]["error_code"] == "provider_unavailable"
    assert attempts[0]["retryable"] is True
    assert attempts[1]["is_final"] is True
    assert attempts[0]["provider_name"] == "OpenAI Primary"
    assert attempts[0]["endpoint_path"] == "/chat/completions"
    assert attempts[0]["credential_label"] == "primary"

    missing = await client.get("/api/v1/usage/requests/req-nope", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "request_not_found"


# --------------------------------------------------------------------------- #
# Exports
# --------------------------------------------------------------------------- #
async def test_csv_export_has_a_bom_and_one_row_per_attempt(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    response = await client.get(
        "/api/v1/usage/export?format=csv&date_from=2000-01-01", headers=headers
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["x-row-count"] == "3"

    text = response.text
    assert text.startswith("\ufeff")
    rows = list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))
    assert len(rows) == 3
    assert rows[0]["provider_name"] == "OpenAI Primary"
    assert rows[0]["api_key_name"] == "سرویس پشتیبانی"
    assert {"request_id", "attempt_number", "cost_usd", "created_at"} <= set(rows[0])


async def test_json_export_is_utf8_and_keeps_persian_labels(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    response = await client.get(
        "/api/v1/usage/export?format=json&date_from=2000-01-01", headers=headers
    )
    payload = json.loads(response.text)
    assert len(payload) == 3
    assert payload[0]["api_key_name"] == "سرویس پشتیبانی"
    assert response.headers["x-row-count"] == "3"


async def test_export_respects_the_provider_filter(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    ids = await _fixture(session_factory)

    response = await client.get(
        f"/api/v1/usage/export?format=json&provider_id={uuid.uuid4()}&date_from=2000-01-01",
        headers=headers,
    )
    assert json.loads(response.text) == []

    mine = await client.get(
        f"/api/v1/usage/export?format=json&provider_id={ids['provider']}&date_from=2000-01-01",
        headers=headers,
    )
    assert len(json.loads(mine.text)) == 3


# --------------------------------------------------------------------------- #
# Rollups and permissions
# --------------------------------------------------------------------------- #
async def test_rollup_rebuild_writes_the_daily_dimension(client, session_factory, session) -> None:
    from sqlalchemy import select

    from app.models.usage import UsageDailyRollup

    headers = await _headers(client, session_factory)
    await _fixture(session_factory)

    today = datetime.now(UTC).date().isoformat()
    response = await client.post(f"/api/v1/usage/rollups/rebuild?day={today}", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["rows"] == 1

    rollups = (await session.execute(select(UsageDailyRollup))).scalars().all()
    assert len(rollups) == 1
    assert rollups[0].requests == 3
    assert rollups[0].tokens == 150

    # Re-running is idempotent: one row per dimension, not a second one.
    again = await client.post(f"/api/v1/usage/rollups/rebuild?day={today}", headers=headers)
    assert again.json()["rows"] == 1
    assert len((await session.execute(select(UsageDailyRollup))).scalars().all()) == 1


async def test_viewer_may_read_but_not_rebuild_rollups(client, session_factory) -> None:
    await create_user(session_factory)
    await create_user(session_factory, email="viewer@xerex.ai", role=AdminRole.VIEWER)
    viewer_headers = {"Authorization": f"Bearer {await login(client, 'viewer@xerex.ai')}"}

    assert (await client.get("/api/v1/usage/summary", headers=viewer_headers)).status_code == 200
    assert (
        await client.get("/api/v1/usage/export?format=csv", headers=viewer_headers)
    ).status_code == 200
    denied = await client.post("/api/v1/usage/rollups/rebuild", headers=viewer_headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_role"


async def test_usage_requires_authentication(client) -> None:
    assert (await client.get("/api/v1/usage/summary")).status_code == 401
