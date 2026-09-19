"""Provider → credential → model → endpoint relationships (item 7).

The scenario the schema must express, from the correction directive:

    Model A
      Endpoint 1 → Provider X → Credential 1
      Endpoint 2 → Provider X → Credential 2
      Endpoint 3 → Provider Y → Credential 1

Key properties:

* an endpoint is bound to a credential explicitly and independently of its
  provider-level default;
* one provider can have several credentials, and different endpoints can use
  different ones;
* a credential row can back endpoints of more than one provider without the secret
  being duplicated;
* ``None`` keeps the M1 behaviour: the provider's default credential is used.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.core.crypto import encrypt_secret
from app.models.enums import CredentialStatus, ProviderKind
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.services.providers import (
    effective_provider_id,
    list_routing_targets,
    pick_credential,
    resolve_endpoint_target,
)


@pytest.fixture
async def matrix(session_factory) -> dict[str, uuid.UUID]:
    """Seed the exact scenario from the directive."""
    async with session_factory() as session:
        provider_x = Provider(
            name="Provider X",
            slug="provider-x",
            kind=ProviderKind.OPENAI,
            base_url="https://x.example/v1",
        )
        provider_y = Provider(
            name="Provider Y",
            slug="provider-y",
            kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://y.example/v1",
        )
        session.add_all([provider_x, provider_y])
        await session.flush()

        credential_1 = ProviderCredential(
            provider_id=provider_x.id,
            label="Credential 1",
            encrypted_secret=encrypt_secret("sk-x-credential-1"),
            key_hint="…tial-1",
            status=CredentialStatus.ACTIVE,
        )
        credential_2 = ProviderCredential(
            provider_id=provider_x.id,
            label="Credential 2",
            encrypted_secret=encrypt_secret("sk-x-credential-2"),
            key_hint="…tial-2",
            status=CredentialStatus.ACTIVE,
        )
        session.add_all([credential_1, credential_2])
        await session.flush()

        model = Model(provider_id=provider_x.id, name="model-a", display_name="Model A")
        session.add(model)
        await session.flush()

        endpoint_1 = ModelEndpoint(
            model_id=model.id, path="/chat/completions", credential_id=credential_1.id
        )
        endpoint_2 = ModelEndpoint(
            model_id=model.id, path="/chat/completions", credential_id=credential_2.id
        )
        endpoint_3 = ModelEndpoint(
            model_id=model.id,
            path="/v1/messages",
            provider_id=provider_y.id,  # different provider than the model's home
            credential_id=credential_1.id,  # same credential row as endpoint 1
        )
        session.add_all([endpoint_1, endpoint_2, endpoint_3])
        await session.commit()

        return {
            "provider_x": provider_x.id,
            "provider_y": provider_y.id,
            "credential_1": credential_1.id,
            "credential_2": credential_2.id,
            "model": model.id,
            "endpoint_1": endpoint_1.id,
            "endpoint_2": endpoint_2.id,
            "endpoint_3": endpoint_3.id,
        }


async def test_every_endpoint_resolves_to_its_own_provider_and_credential(
    session_factory, matrix
) -> None:
    async with session_factory() as session:
        targets = await list_routing_targets(session, model_id=matrix["model"])

    by_endpoint = {target.endpoint.id: target for target in targets}
    assert set(by_endpoint) == {matrix["endpoint_1"], matrix["endpoint_2"], matrix["endpoint_3"]}

    first = by_endpoint[matrix["endpoint_1"]]
    assert first.provider.id == matrix["provider_x"]
    assert first.credential is not None and first.credential.id == matrix["credential_1"]
    assert first.credential_source == "endpoint"

    second = by_endpoint[matrix["endpoint_2"]]
    assert second.provider.id == matrix["provider_x"]
    assert second.credential is not None and second.credential.id == matrix["credential_2"]

    third = by_endpoint[matrix["endpoint_3"]]
    assert third.provider.id == matrix["provider_y"]  # endpoint-level provider override
    assert third.provider_source == "endpoint"
    assert third.credential is not None and third.credential.id == matrix["credential_1"]


async def test_credential_row_is_reused_and_never_duplicated(session_factory, matrix) -> None:
    async with session_factory() as session:
        targets = await list_routing_targets(session, model_id=matrix["model"])
        credential_count = (
            await session.execute(select(func.count()).select_from(ProviderCredential))
        ).scalar_one()

    assert credential_count == 2  # three endpoints, but only two stored secrets
    used = {target.credential.id for target in targets if target.credential is not None}
    assert used == {matrix["credential_1"], matrix["credential_2"]}


async def test_one_provider_can_have_many_credentials(session_factory, matrix) -> None:
    async with session_factory() as session:
        credentials = (
            (
                await session.execute(
                    select(ProviderCredential).where(
                        ProviderCredential.provider_id == matrix["provider_x"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert {credential.id for credential in credentials} == {
        matrix["credential_1"],
        matrix["credential_2"],
    }


async def test_missing_endpoint_credential_falls_back_to_the_provider_default(
    session_factory, matrix
) -> None:
    async with session_factory() as session:
        endpoint = ModelEndpoint(model_id=matrix["model"], path="/embeddings")
        session.add(endpoint)
        await session.commit()
        await session.refresh(endpoint)

        targets = await list_routing_targets(session, model_id=matrix["model"])
        fallback = next(target for target in targets if target.endpoint.id == endpoint.id)

    assert fallback.credential is not None
    assert fallback.credential.provider_id == matrix["provider_x"]
    assert fallback.credential_source == "provider"


async def test_disabled_endpoints_are_excluded_when_requested(session_factory, matrix) -> None:
    async with session_factory() as session:
        endpoint = await session.get(ModelEndpoint, matrix["endpoint_2"])
        assert endpoint is not None
        endpoint.enabled = False
        await session.commit()

        enabled_targets = await list_routing_targets(session, model_id=matrix["model"])
        all_targets = await list_routing_targets(
            session, model_id=matrix["model"], enabled_only=False
        )

    assert matrix["endpoint_2"] not in {target.endpoint.id for target in enabled_targets}
    assert matrix["endpoint_2"] in {target.endpoint.id for target in all_targets}


async def test_resolve_endpoint_target_uses_the_override(session_factory, matrix) -> None:
    async with session_factory() as session:
        endpoint = await session.get(ModelEndpoint, matrix["endpoint_3"])
        assert endpoint is not None
        target = await resolve_endpoint_target(session, endpoint)

    assert target is not None
    assert target.provider.id == matrix["provider_y"]
    assert target.credential is not None and target.credential.id == matrix["credential_1"]


def test_effective_provider_id_prefers_the_endpoint_override() -> None:
    home = uuid.uuid4()
    other = uuid.uuid4()
    model = Model(id=uuid.uuid4(), provider_id=home, name="m")
    endpoint = ModelEndpoint(id=uuid.uuid4(), model_id=model.id, path="/x")
    assert effective_provider_id(endpoint=endpoint, model=model) == home
    endpoint.provider_id = other
    assert effective_provider_id(endpoint=endpoint, model=model) == other


def test_pick_credential_returns_none_when_the_binding_is_dangling() -> None:
    provider = Provider(id=uuid.uuid4(), name="P", slug="p", kind=ProviderKind.OPENAI, base_url="u")
    endpoint = ModelEndpoint(
        id=uuid.uuid4(), model_id=uuid.uuid4(), path="/x", credential_id=uuid.uuid4()
    )
    assert pick_credential(endpoint=endpoint, provider=provider, credentials=[]) is None
