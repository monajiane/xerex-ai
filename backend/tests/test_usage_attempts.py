"""Client request vs. routing attempts (correction pass item 9).

The gateway must be able to express:

    one client request → attempt 1 (failed) → attempt 2 (succeeded)

with tokens/cost per attempt *and* an aggregated view per request, without a
destructive redesign in M4.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.crypto import encrypt_secret
from app.models.enums import ClientRequestState, ProviderKind
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.models.usage import ApiKey, ClientRequest, UsageRecord


@pytest.fixture
async def request_with_attempts(session_factory) -> dict[str, object]:
    async with session_factory() as session:
        provider = Provider(
            name="Provider X",
            slug="provider-x",
            kind=ProviderKind.OPENAI,
            base_url="https://x.example/v1",
        )
        other_provider = Provider(
            name="Provider Y",
            slug="provider-y",
            kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://y.example/v1",
        )
        session.add_all([provider, other_provider])
        await session.flush()

        credential = ProviderCredential(
            provider_id=provider.id,
            label="Credential 1",
            encrypted_secret=encrypt_secret("sk-1"),
            key_hint="…al-1",
        )
        session.add(credential)
        await session.flush()

        model = Model(provider_id=provider.id, name="model-a")
        session.add(model)
        await session.flush()

        endpoint = ModelEndpoint(model_id=model.id, path="/chat/completions")
        session.add(endpoint)

        api_key = ApiKey(name="console", prefix="xrx_live_test1", hash="a" * 64)
        session.add(api_key)
        await session.flush()

        started = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
        client_request = ClientRequest(
            request_id="req_9f2a1c",
            api_key_id=api_key.id,
            requested_model="model-a",
            state=ClientRequestState.PENDING,
            started_at=started,
        )
        session.add(client_request)
        await session.flush()

        first_attempt = UsageRecord(
            request_id="req_9f2a1c",
            client_request_id=client_request.id,
            attempt_number=1,
            is_final=False,
            retryable=True,
            api_key_id=api_key.id,
            provider_id=provider.id,
            credential_id=credential.id,
            model_id=model.id,
            endpoint_id=endpoint.id,
            input_tokens=120,
            output_tokens=0,
            total_tokens=120,
            cost=Decimal("0.00042000"),
            latency_ms=900,
            status_code=429,
            error_code="rate_limit_exceeded",
            created_at=started,
        )
        second_provider_attempt = UsageRecord(
            request_id="req_9f2a1c",
            client_request_id=client_request.id,
            attempt_number=2,
            is_final=True,
            retryable=False,
            api_key_id=api_key.id,
            provider_id=other_provider.id,
            credential_id=credential.id,  # same credential row, different provider
            model_id=model.id,
            endpoint_id=endpoint.id,
            input_tokens=120,
            output_tokens=80,
            total_tokens=200,
            cost=Decimal("0.00110000"),
            latency_ms=1500,
            status_code=200,
            created_at=started,
        )
        session.add_all([first_attempt, second_provider_attempt])

        client_request.state = ClientRequestState.SUCCEEDED
        client_request.attempt_count = 2
        client_request.input_tokens = 120
        client_request.output_tokens = 80
        client_request.total_tokens = 200
        client_request.cost = Decimal("0.00152000")
        client_request.latency_ms = 2400
        client_request.final_status_code = 200
        client_request.completed_at = started
        await session.commit()

        return {
            "client_request": client_request.id,
            "request_id": "req_9f2a1c",
            "provider": provider.id,
            "api_key": api_key.id,
        }


async def test_one_client_request_with_two_attempts(session_factory, request_with_attempts) -> None:
    async with session_factory() as session:
        client_request = (
            await session.execute(
                select(ClientRequest)
                .where(ClientRequest.id == request_with_attempts["client_request"])
                .options(selectinload(ClientRequest.attempts))
            )
        ).scalar_one()

    assert client_request.state is ClientRequestState.SUCCEEDED
    assert client_request.attempt_count == 2
    assert [attempt.attempt_number for attempt in client_request.attempts] == [1, 2]
    assert [attempt.is_final for attempt in client_request.attempts] == [False, True]
    assert client_request.attempts[0].retryable is True
    assert client_request.attempts[0].status_code == 429
    assert client_request.attempts[1].cost == Decimal("0.00110000")
    assert client_request.total_tokens == 200
    assert client_request.latency_ms == 2400


async def test_attempts_track_credential_and_provider_per_attempt(
    session_factory, request_with_attempts
) -> None:
    async with session_factory() as session:
        rows = (
            (await session.execute(select(UsageRecord).order_by(UsageRecord.attempt_number.asc())))
            .scalars()
            .all()
        )

    assert [row.request_id for row in rows] == ["req_9f2a1c", "req_9f2a1c"]  # not unique anymore
    assert rows[0].provider_id != rows[1].provider_id
    assert rows[0].credential_id == rows[1].credential_id  # one secret, two providers
    assert rows[0].endpoint_id is not None


async def test_request_id_is_no_longer_unique_but_attempt_number_is(
    session_factory, request_with_attempts
) -> None:
    async with session_factory() as session:
        duplicates = (
            await session.execute(
                select(func.count())
                .select_from(UsageRecord)
                .where(UsageRecord.request_id == request_with_attempts["request_id"])
            )
        ).scalar_one()
    assert duplicates == 2

    indexes = {index.name: index for index in UsageRecord.__table__.indexes}
    assert "ix_usage_records_request_id" in indexes
    assert indexes["ix_usage_records_request_id"].unique is False
    unique_constraints = {constraint.name for constraint in UsageRecord.__table__.constraints}
    assert "uq_usage_records_attempt_number" in unique_constraints


async def test_duplicate_attempt_numbers_are_rejected(
    session_factory, request_with_attempts
) -> None:
    async with session_factory() as session:
        session.add(
            UsageRecord(
                request_id="req_9f2a1c",
                client_request_id=request_with_attempts["client_request"],
                attempt_number=1,  # already taken
                created_at=datetime(2026, 9, 18, 11, 0, tzinfo=UTC),
            )
        )
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


async def test_deleting_a_client_request_cascades_to_attempts(
    session_factory, request_with_attempts
) -> None:
    async with session_factory() as session:
        client_request = (
            await session.execute(
                select(ClientRequest)
                .where(ClientRequest.id == request_with_attempts["client_request"])
                .options(selectinload(ClientRequest.attempts))
            )
        ).scalar_one()
        await session.delete(client_request)
        await session.commit()

        remaining = (
            await session.execute(select(func.count()).select_from(UsageRecord))
        ).scalar_one()
        orphan_pointer = UsageRecord.__table__.c.client_request_id.foreign_keys

    assert remaining == 0
    assert next(iter(orphan_pointer)).ondelete == "CASCADE"


def test_schema_exposes_attempt_columns_and_safe_deletes() -> None:
    columns = set(UsageRecord.__table__.c.keys())
    assert {
        "client_request_id",
        "attempt_number",
        "is_final",
        "retryable",
        "credential_id",
        "endpoint_id",
    } <= columns

    for column in ("provider_id", "model_id", "credential_id", "endpoint_id", "api_key_id"):
        foreign_key = next(iter(UsageRecord.__table__.c[column].foreign_keys))
        assert foreign_key.ondelete == "SET NULL"

    client_request_columns = set(ClientRequest.__table__.c.keys())
    assert {
        "request_id",
        "state",
        "attempt_count",
        "final_status_code",
        "final_error_code",
        "started_at",
        "completed_at",
    } <= client_request_columns


async def test_attempt_rows_are_still_valid_without_a_parent_request(session_factory) -> None:
    """A standalone attempt (no client request) must remain insertable."""
    async with session_factory() as session:
        record = UsageRecord(request_id="req_orphan", created_at=datetime.now(UTC))
        session.add(record)
        await session.commit()
        await session.refresh(record)

    assert record.client_request_id is None
    assert record.attempt_number == 1
    assert record.status_code == 200
    assert isinstance(uuid.uuid4(), uuid.UUID)
