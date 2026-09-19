"""Endpoint ↔ provider ↔ credential resolution for the future routing engine.

The architectural rule this module implements: **a routing decision picks a
provider, a credential, a model and an endpoint independently.** Nothing here
contacts an upstream provider — that is M2/M5. It answers "which provider and
credential would an attempt through this endpoint use?", which is what makes
failover across providers, credentials and endpoints possible later.

Effective provider
------------------

``model_endpoints.provider_id`` (optional) overrides the model's home provider, so
"Model A, endpoint 3, through provider Y" is expressible without duplicating the
model row.

Credential precedence
---------------------

1. ``model_endpoints.credential_id`` — an explicit, per-endpoint binding;
2. otherwise the effective provider's first credential as its default;
3. otherwise no credential (the caller must treat the target as unusable).

A credential row may be referenced by endpoints of more than one provider; secrets
are never copied, only referenced.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential


@dataclass(frozen=True)
class RoutingTarget:
    """One candidate an attempt could be made through."""

    provider: Provider
    credential: ProviderCredential | None
    model: Model
    endpoint: ModelEndpoint

    @property
    def provider_source(self) -> str:
        """``endpoint`` when the endpoint overrides the model's home provider."""
        return "endpoint" if self.endpoint.provider_id is not None else "model"

    @property
    def credential_source(self) -> str:
        """``endpoint`` | ``provider`` | ``none`` — why this credential was chosen."""
        if self.credential is None:
            return "none"
        return "endpoint" if self.endpoint.credential_id is not None else "provider"


def effective_provider_id(*, endpoint: ModelEndpoint, model: Model) -> uuid.UUID:
    """Provider an attempt through ``endpoint`` is actually sent to."""
    return endpoint.provider_id or model.provider_id


def pick_credential(
    *,
    endpoint: ModelEndpoint,
    provider: Provider,
    credentials: list[ProviderCredential],
) -> ProviderCredential | None:
    """Pure precedence rule shared by the API, tests and the M5 engine."""
    if endpoint.credential_id is not None:
        for credential in credentials:
            if credential.id == endpoint.credential_id:
                return credential
        return None
    for credential in credentials:
        if credential.provider_id == provider.id:
            return credential
    return None


def build_target(
    *,
    model: Model,
    endpoint: ModelEndpoint,
    providers: dict[uuid.UUID, Provider],
    credentials: list[ProviderCredential],
) -> RoutingTarget | None:
    """Resolve one endpoint into a routing target, or ``None`` when unresolvable."""
    provider = providers.get(effective_provider_id(endpoint=endpoint, model=model))
    if provider is None:
        return None
    return RoutingTarget(
        provider=provider,
        credential=pick_credential(endpoint=endpoint, provider=provider, credentials=credentials),
        model=model,
        endpoint=endpoint,
    )


async def list_routing_targets(
    session: AsyncSession,
    *,
    model_id: uuid.UUID,
    enabled_only: bool = True,
) -> list[RoutingTarget]:
    """Every way this model can be reached, with provider and credential resolved.

    Disabled endpoints, disabled or deprecated models and disabled providers are
    skipped when ``enabled_only`` is true.
    """
    model = await session.get(Model, model_id)
    if model is None:
        return []
    if enabled_only and (not model.enabled or model.deprecated):
        return []

    providers = {
        provider.id: provider
        for provider in (await session.execute(select(Provider))).scalars().all()
    }
    credentials = list(
        (
            await session.execute(
                select(ProviderCredential).order_by(ProviderCredential.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    endpoints = list(
        (
            await session.execute(
                select(ModelEndpoint)
                .where(ModelEndpoint.model_id == model_id)
                .order_by(ModelEndpoint.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    targets: list[RoutingTarget] = []
    for endpoint in endpoints:
        if enabled_only and not endpoint.enabled:
            continue
        target = build_target(
            model=model, endpoint=endpoint, providers=providers, credentials=credentials
        )
        if target is None:
            continue
        if enabled_only and not target.provider.enabled:
            continue
        targets.append(target)
    return targets


async def resolve_endpoint_target(
    session: AsyncSession, endpoint: ModelEndpoint
) -> RoutingTarget | None:
    """Provider + credential an attempt through ``endpoint`` would use (no upstream call)."""
    model = await session.get(Model, endpoint.model_id)
    if model is None:
        return None
    providers = {
        provider.id: provider
        for provider in (await session.execute(select(Provider))).scalars().all()
    }
    credentials = list((await session.execute(select(ProviderCredential))).scalars().all())
    return build_target(
        model=model, endpoint=endpoint, providers=providers, credentials=credentials
    )
