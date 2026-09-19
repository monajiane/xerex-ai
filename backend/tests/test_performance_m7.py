"""M7 hardening: query budgets and index coverage.

Aggregates are the easiest place to hide an N+1: a request log with ten failover
attempts once resolved its provider/model/credential/endpoint labels per attempt. These
tests bound the number of statements an endpoint may issue, so a future refactor that
reintroduces per-row lookups fails here instead of in production.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event

from app.core.crypto import encrypt_secret, key_hint
from app.models.enums import CredentialStatus, HealthStatus
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.models.usage import ApiKey, ClientRequest, UsageRecord
from tests.conftest import create_user, login


@pytest.fixture
def statement_counter(engine):
    """Counts SQL statements executed on the test engine for the duration of a test."""
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)


async def _seed(session_factory, *, attempts: int = 1) -> dict[str, uuid.UUID]:
    """One provider, model, endpoint, key and a failing request with N attempts."""
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
            max_retries=5,
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
            prefix="xrx_live_perf0001",
            hash="hash-perf-0001",
            scopes=["chat"],
            enabled=True,
        )
        session.add_all([endpoint, api_key])
        await session.flush()

        now = datetime.now(UTC)
        request = ClientRequest(
            request_id="req-perf-1",
            api_key_id=api_key.id,
            requested_model="gpt-4o-mini",
            state="failed",
            attempt_count=attempts,
            latency_ms=900,
            total_tokens=150,
            final_status_code=503,
            final_error_code="provider_unavailable",
            started_at=now - timedelta(minutes=5),
            completed_at=now - timedelta(minutes=5),
        )
        session.add(request)
        await session.flush()

        for number in range(1, attempts + 1):
            session.add(
                UsageRecord(
                    request_id="req-perf-1",
                    client_request_id=request.id,
                    attempt_number=number,
                    is_final=number == attempts,
                    retryable=number < attempts,
                    api_key_id=api_key.id,
                    provider_id=provider.id,
                    credential_id=credential.id,
                    model_id=model.id,
                    endpoint_id=endpoint.id,
                    total_tokens=150 if number == attempts else 0,
                    latency_ms=100 * number,
                    status_code=503 if number < attempts else 200,
                    error_code=None if number == attempts else "provider_unavailable",
                    created_at=now - timedelta(minutes=5),
                )
            )
        await session.commit()
        return {"provider": provider.id, "model": model.id}


async def _headers(client, session_factory) -> dict[str, str]:
    await create_user(session_factory)
    return {"Authorization": f"Bearer {await login(client)}"}


async def test_summary_stays_within_its_query_budget(
    client, session_factory, statement_counter
) -> None:
    headers = await _headers(client, session_factory)
    await _seed(session_factory, attempts=6)

    statement_counter.clear()
    response = await client.get("/api/v1/usage/summary?date_from=2000-01-01", headers=headers)
    assert response.status_code == 200

    # totalling, p95, series — plus session plumbing; never one query per row.
    assert len(statement_counter) <= 8, statement_counter


async def test_request_detail_labels_are_fetched_in_bulk(
    client, session_factory, statement_counter
) -> None:
    headers = await _headers(client, session_factory)
    await _seed(session_factory, attempts=8)

    statement_counter.clear()
    response = await client.get("/api/v1/usage/requests/req-perf-1", headers=headers)
    assert response.status_code == 200
    assert len(response.json()["attempts"]) == 8

    # request + attempts + one label query per entity type (4) — not 8 × 4.
    assert len(statement_counter) <= 8, statement_counter


async def test_request_log_page_does_not_query_per_row(
    client, session_factory, statement_counter
) -> None:
    headers = await _headers(client, session_factory)
    await _seed(session_factory, attempts=5)

    statement_counter.clear()
    response = await client.get("/api/v1/usage/requests?date_from=2000-01-01", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert len(statement_counter) <= 8, statement_counter


def test_analytics_indexes_cover_the_m6_access_patterns() -> None:
    """The indexes migration 0003 creates must stay declared on the models."""
    usage_indexes = {index.name: index for index in UsageRecord.__table__.indexes}
    assert "ix_usage_records_created_at" in usage_indexes
    created_at = usage_indexes["ix_usage_records_created_at"]
    assert [column.name for column in created_at.columns] == ["created_at", "id"]

    final_attempt = usage_indexes["ix_usage_records_final_attempt"]
    assert [column.name for column in final_attempt.columns] == ["client_request_id"]
    assert final_attempt.dialect_options["sqlite"]["where"] is not None
    assert final_attempt.dialect_options["postgresql"]["where"] is not None

    request_indexes = {index.name for index in ClientRequest.__table__.indexes}
    assert "ix_client_requests_started_at" in request_indexes
