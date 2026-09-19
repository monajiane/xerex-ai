"""Health abstraction across provider, credential, model and endpoint (item 8).

The directive's example, recorded and read back:

    Provider X   = healthy
    Credential 1 = rate_limited
    Credential 2 = healthy
    Model A      = healthy
    Endpoint A   = degraded

No scheduler, no worker: the schema and the write path exist, the current system
health endpoints keep working.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.crypto import encrypt_secret
from app.health.targets import (
    HEALTH_TARGET_KINDS,
    HealthTarget,
    health_history,
    latest_health_check,
    record_health_check,
)
from app.models.enums import CredentialStatus, HealthStatus, HealthTargetType, ProviderKind
from app.models.health import HealthCheck
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential


@pytest.fixture
async def entities(session_factory) -> dict[str, uuid.UUID]:
    async with session_factory() as session:
        provider = Provider(
            name="Provider X",
            slug="provider-x",
            kind=ProviderKind.OPENAI,
            base_url="https://x.example/v1",
        )
        session.add(provider)
        await session.flush()

        credential_1 = ProviderCredential(
            provider_id=provider.id,
            label="Credential 1",
            encrypted_secret=encrypt_secret("sk-1"),
            key_hint="…al-1",
            status=CredentialStatus.ACTIVE,
        )
        credential_2 = ProviderCredential(
            provider_id=provider.id,
            label="Credential 2",
            encrypted_secret=encrypt_secret("sk-2"),
            key_hint="…al-2",
            status=CredentialStatus.ACTIVE,
        )
        session.add_all([credential_1, credential_2])
        await session.flush()

        model = Model(provider_id=provider.id, name="model-a")
        session.add(model)
        await session.flush()

        endpoint = ModelEndpoint(model_id=model.id, path="/chat/completions")
        session.add(endpoint)
        await session.commit()

        return {
            "provider": provider.id,
            "credential_1": credential_1.id,
            "credential_2": credential_2.id,
            "model": model.id,
            "endpoint": endpoint.id,
        }


def test_the_four_health_dimensions_are_declared() -> None:
    assert HEALTH_TARGET_KINDS == ("provider", "credential", "model", "endpoint")


async def test_record_and_read_back_each_dimension(session_factory, entities) -> None:
    async with session_factory() as session:
        await record_health_check(
            session, HealthTarget.provider(entities["provider"]), status=HealthStatus.HEALTHY
        )
        await record_health_check(
            session,
            HealthTarget.credential(entities["credential_1"], provider_id=entities["provider"]),
            status=HealthStatus.RATE_LIMITED,
            status_code=429,
            error_code="rate_limit_exceeded",
        )
        await record_health_check(
            session,
            HealthTarget.credential(entities["credential_2"], provider_id=entities["provider"]),
            status=HealthStatus.HEALTHY,
        )
        await record_health_check(
            session, HealthTarget.model(entities["model"]), status=HealthStatus.HEALTHY
        )
        await record_health_check(
            session,
            HealthTarget.endpoint(
                entities["endpoint"],
                model_id=entities["model"],
                provider_id=entities["provider"],
            ),
            status=HealthStatus.DEGRADED,
            latency_ms=4200,
        )
        await session.commit()

        provider_check = await latest_health_check(
            session, HealthTarget.provider(entities["provider"])
        )
        credential_check = await latest_health_check(
            session, HealthTarget.credential(entities["credential_1"])
        )
        endpoint_check = await latest_health_check(
            session, HealthTarget.endpoint(entities["endpoint"])
        )

    assert provider_check is not None and provider_check.status is HealthStatus.HEALTHY
    assert credential_check is not None
    assert credential_check.status is HealthStatus.RATE_LIMITED
    assert credential_check.status_code == 429
    assert endpoint_check is not None
    assert endpoint_check.status is HealthStatus.DEGRADED
    assert endpoint_check.latency_ms == 4200


async def test_typed_columns_and_generic_pointer_stay_in_sync(session_factory, entities) -> None:
    async with session_factory() as session:
        entry = await record_health_check(
            session,
            HealthTarget.credential(entities["credential_1"], provider_id=entities["provider"]),
            status=HealthStatus.DEGRADED,
        )
        await session.commit()
        assert entry.target_type is HealthTargetType.CREDENTIAL
        assert entry.target_id == entities["credential_1"]
        assert entry.credential_id == entities["credential_1"]
        assert entry.provider_id == entities["provider"]
        assert entry.model_id is None
        assert entry.endpoint_id is None


async def test_history_is_filtered_by_dimension_and_ordered(session_factory, entities) -> None:
    base = datetime(2026, 9, 18, 10, 0, tzinfo=UTC)
    async with session_factory() as session:
        for offset, status in enumerate(
            [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.RATE_LIMITED]
        ):
            await record_health_check(
                session,
                HealthTarget.credential(entities["credential_1"]),
                status=status,
                checked_at=base + timedelta(minutes=offset),
            )
        await record_health_check(
            session, HealthTarget.provider(entities["provider"]), status=HealthStatus.HEALTHY
        )
        await session.commit()

        credential_history = await health_history(session, kind=HealthTargetType.CREDENTIAL)
        latest = await latest_health_check(
            session, HealthTarget.credential(entities["credential_1"])
        )
        total = (await session.execute(select(func.count()).select_from(HealthCheck))).scalar_one()

    assert total == 4
    assert len(credential_history) == 3
    assert all(entry.target_type is HealthTargetType.CREDENTIAL for entry in credential_history)
    assert latest is not None and latest.status is HealthStatus.RATE_LIMITED


async def test_health_rows_reference_real_entities(session_factory, entities) -> None:
    async with session_factory() as session:
        entry = await record_health_check(
            session,
            HealthTarget.endpoint(entities["endpoint"], model_id=entities["model"]),
            status=HealthStatus.UNKNOWN,
        )
        await session.commit()

        fk_targets = {
            fk.parent.name: fk.column.table.name
            for fk in entry.__table__.columns["endpoint_id"].foreign_keys
        }
        assert fk_targets == {"endpoint_id": "model_endpoints"}
        assert entry.endpoint_id is not None


def test_target_constructor_requires_the_matching_identifier() -> None:
    identifier = uuid.uuid4()
    target = HealthTarget.model(identifier, provider_id=uuid.uuid4())
    assert target.typed_columns()["model_id"] == identifier
    assert target.describe()["target_type"] == "model"
