"""Demo data for the Persian admin panel (M7).

Seeding writes what the panel needs to look alive — providers, credentials, models,
endpoints, a routing rule, an API key, health observations and a week of usage — while
staying obviously artificial:

* provider/model names carry the ``(demo)`` suffix and slugs end in ``-demo``;
* credentials hold placeholder secrets (``sk-demo-...``), never anything real;
* the API key secret is printed once and its prefix is ``xrx_live_demo``;
* usage rows are generated from a fixed, seeded RNG so two runs produce the same picture.

Everything is idempotent: running the seed twice updates instead of duplicating, and
``reset_demo`` deletes only rows that carry the demo markers.
"""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_secret, key_hint
from app.core.security import hash_password
from app.models.enums import (
    AdminRole,
    ClientRequestState,
    CredentialStatus,
    HealthStatus,
    RoutingStrategy,
)
from app.models.health import HealthCheck
from app.models.identity import AdminUser
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.models.routing import RoutingRule
from app.models.usage import ApiKey, ClientRequest, UsageRecord
from app.services.api_keys import KNOWN_SCOPES

#: Marker appended to every seeded provider/model name.
DEMO_SUFFIX = "(demo)"
#: Prefix of the single demo API key; its secret is shown once by the CLI.
DEMO_KEY_PREFIX = "xrx_live_demo"
DEMO_ADMIN_EMAIL = "demo@xerex.ai"
DEMO_ADMIN_PASSWORD = "xerex-demo-owner-2026"

_SEED = 20260919


@dataclass
class SeedReport:
    """What a seed run actually wrote, so the CLI can print facts instead of promises."""

    users: int = 0
    providers: int = 0
    credentials: int = 0
    models: int = 0
    endpoints: int = 0
    routing_rules: int = 0
    api_keys: int = 0
    health_checks: int = 0
    requests: int = 0
    attempts: int = 0
    api_key_secret: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "users": self.users,
            "providers": self.providers,
            "credentials": self.credentials,
            "models": self.models,
            "endpoints": self.endpoints,
            "routing_rules": self.routing_rules,
            "api_keys": self.api_keys,
            "health_checks": self.health_checks,
            "requests": self.requests,
            "attempts": self.attempts,
            "api_key_secret": self.api_key_secret,
            "notes": self.notes,
        }


async def seed_demo(
    session: AsyncSession,
    *,
    days: int = 7,
    with_traffic: bool = True,
    requests_per_day: int = 24,
) -> SeedReport:
    """Create (or refresh) the demo dataset and return what was written."""
    report = SeedReport()
    rng = random.Random(_SEED)
    now = datetime.now(UTC)

    owner = await _ensure_demo_owner(session, report)
    openai = await _ensure_provider(
        session,
        report,
        slug=f"openai-primary-{_slug(DEMO_SUFFIX)}",
        name=f"OpenAI Primary {DEMO_SUFFIX}",
        kind="openai",
        base_url="https://api.openai.com/v1",
        priority=1,
        weight=100,
        description="Seeded demo provider. Replace or delete before serving real traffic.",
    )
    backup = await _ensure_provider(
        session,
        report,
        slug=f"backup-gateway-{_slug(DEMO_SUFFIX)}",
        name=f"Backup Gateway {DEMO_SUFFIX}",
        kind="openai_compatible",
        base_url="https://gateway.example.com/v1",
        priority=5,
        weight=50,
        description="Seeded demo provider used to show failover and routing decisions.",
    )

    credential = await _ensure_credential(session, report, openai, label="primary")
    backup_credential = await _ensure_credential(session, report, backup, label="backup")

    model_specs = (
        ("gpt-4o-mini", "GPT-4o mini", 128_000, 0.15, 0.6),
        ("gpt-4o", "GPT-4o", 128_000, 2.5, 10.0),
    )
    models: list[Model] = []
    for name, display, context, input_price, output_price in model_specs:
        model = await _ensure_model(
            session,
            report,
            openai,
            name=name,
            display_name=display,
            context_window=context,
            input_price=input_price,
            output_price=output_price,
        )
        models.append(model)
        await _ensure_endpoint(session, report, model, openai, credential)

    backup_model = await _ensure_model(
        session,
        report,
        backup,
        name="gpt-4o-mini",
        display_name="GPT-4o mini (backup)",
        context_window=128_000,
        input_price=0.2,
        output_price=0.8,
    )
    models.append(backup_model)
    await _ensure_endpoint(session, report, backup_model, backup, backup_credential)

    await _ensure_routing_rule(session, report, models)
    api_key, secret = await _ensure_api_key(session, report)
    report.api_key_secret = secret

    for provider in (openai, backup):
        await _ensure_health_check(session, report, provider, now)

    if with_traffic:
        await _ensure_traffic(
            session,
            report,
            rng,
            provider=openai,
            credential=credential,
            model=models[0],
            api_key=api_key,
            days=days,
            per_day=requests_per_day,
            now=now,
        )

    await session.commit()
    report.notes.append(
        "Demo rows are marked with '(demo)' / '-demo' and can be removed with "
        "`python -m app.seeds --reset`."
    )
    if owner is None:  # pragma: no cover - defensive
        report.notes.append("Owner account already existed; it was left untouched.")
    return report


async def reset_demo(session: AsyncSession) -> dict[str, int]:
    """Delete everything the seed created, identified by the demo markers.

    Deletion follows the foreign keys: attempts belong to client requests, both belong
    to the demo key, and health rows belong to the demo providers.
    """
    provider_ids = select(Provider.id).where(Provider.slug.like(f"%-{_slug(DEMO_SUFFIX)}"))
    model_ids = select(Model.id).where(Model.provider_id.in_(provider_ids))
    key_ids = select(ApiKey.id).where(ApiKey.prefix.like(f"{DEMO_KEY_PREFIX}%"))
    request_ids = select(ClientRequest.id).where(ClientRequest.api_key_id.in_(key_ids))

    removed = {
        "usage_records": (
            await session.execute(
                delete(UsageRecord).where(UsageRecord.client_request_id.in_(request_ids))
            )
        ).rowcount
        or 0,
        "client_requests": (
            await session.execute(
                delete(ClientRequest).where(ClientRequest.api_key_id.in_(key_ids))
            )
        ).rowcount
        or 0,
        "health_checks": (
            await session.execute(
                delete(HealthCheck).where(HealthCheck.provider_id.in_(provider_ids))
            )
        ).rowcount
        or 0,
        "routing_rules": (
            await session.execute(
                delete(RoutingRule).where(RoutingRule.name.like(f"%{DEMO_SUFFIX}"))
            )
        ).rowcount
        or 0,
        "endpoints": (
            await session.execute(
                delete(ModelEndpoint).where(
                    (ModelEndpoint.provider_id.in_(provider_ids))
                    | (ModelEndpoint.model_id.in_(model_ids))
                )
            )
        ).rowcount
        or 0,
        "models": (
            await session.execute(delete(Model).where(Model.provider_id.in_(provider_ids)))
        ).rowcount
        or 0,
        "credentials": (
            await session.execute(
                delete(ProviderCredential).where(ProviderCredential.provider_id.in_(provider_ids))
            )
        ).rowcount
        or 0,
        "api_keys": (
            await session.execute(delete(ApiKey).where(ApiKey.prefix.like(f"{DEMO_KEY_PREFIX}%")))
        ).rowcount
        or 0,
        "providers": (
            await session.execute(
                delete(Provider).where(Provider.slug.like(f"%-{_slug(DEMO_SUFFIX)}"))
            )
        ).rowcount
        or 0,
        "admin_users": (
            await session.execute(delete(AdminUser).where(AdminUser.email == DEMO_ADMIN_EMAIL))
        ).rowcount
        or 0,
    }
    await session.commit()
    return removed


# --------------------------------------------------------------------------- #
# Pieces
# --------------------------------------------------------------------------- #
def _slug(value: str) -> str:
    return value.strip("()").lower().replace(" ", "-").replace("(", "").replace(")", "")


async def _ensure_demo_owner(session: AsyncSession, report: SeedReport) -> AdminUser | None:
    existing = (
        (await session.execute(select(AdminUser).where(AdminUser.email == DEMO_ADMIN_EMAIL)))
        .scalars()
        .first()
    )
    if existing is not None:
        return None
    owner = AdminUser(
        email=DEMO_ADMIN_EMAIL,
        password_hash=hash_password(DEMO_ADMIN_PASSWORD),
        full_name="Demo Owner",
        role=AdminRole.OWNER,
        status="active",
    )
    session.add(owner)
    report.users += 1
    await session.flush()
    return owner


async def _ensure_provider(
    session: AsyncSession,
    report: SeedReport,
    *,
    slug: str,
    name: str,
    kind: str,
    base_url: str,
    priority: int,
    weight: int,
    description: str,
) -> Provider:
    provider = (
        (await session.execute(select(Provider).where(Provider.slug == slug))).scalars().first()
    )
    if provider is None:
        provider = Provider(
            slug=slug,
            name=name,
            kind=kind,
            base_url=base_url,
            description=description,
            enabled=True,
            priority=priority,
            weight=weight,
            timeout_ms=30_000,
            max_retries=2,
            health_status=HealthStatus.UNKNOWN.value,
        )
        session.add(provider)
        report.providers += 1
        await session.flush()
    return provider


async def _ensure_credential(
    session: AsyncSession, report: SeedReport, provider: Provider, *, label: str
) -> ProviderCredential:
    credential = (
        (
            await session.execute(
                select(ProviderCredential).where(
                    ProviderCredential.provider_id == provider.id,
                    ProviderCredential.label == label,
                )
            )
        )
        .scalars()
        .first()
    )
    if credential is not None:
        return credential
    secret = f"sk-demo-{provider.slug}-{uuid.uuid4().hex[:8]}"
    credential = ProviderCredential(
        provider_id=provider.id,
        label=label,
        encrypted_secret=encrypt_secret(secret),
        key_hint=key_hint(secret),
        status=CredentialStatus.ACTIVE,
    )
    session.add(credential)
    report.credentials += 1
    await session.flush()
    return credential


async def _ensure_model(
    session: AsyncSession,
    report: SeedReport,
    provider: Provider,
    *,
    name: str,
    display_name: str,
    context_window: int,
    input_price: float,
    output_price: float,
) -> Model:
    # The stored name is computed first: the lookup and the insert must agree, or a
    # second run hits the unique constraint instead of returning the existing row.
    stored_name = f"{name}-demo" if provider.kind == "openai_compatible" else name
    model = (
        (
            await session.execute(
                select(Model).where(Model.provider_id == provider.id, Model.name == stored_name)
            )
        )
        .scalars()
        .first()
    )
    if model is not None:
        return model
    model = Model(
        provider_id=provider.id,
        name=stored_name,
        display_name=display_name,
        context_window=context_window,
        max_output_tokens=16_384,
        input_price_per_1m=Decimal(str(input_price)),
        output_price_per_1m=Decimal(str(output_price)),
        capabilities={"streaming": True, "tools": True, "vision": True},
        enabled=True,
    )
    session.add(model)
    report.models += 1
    await session.flush()
    return model


async def _ensure_endpoint(
    session: AsyncSession,
    report: SeedReport,
    model: Model,
    provider: Provider,
    credential: ProviderCredential,
) -> ModelEndpoint:
    endpoint = (
        (await session.execute(select(ModelEndpoint).where(ModelEndpoint.model_id == model.id)))
        .scalars()
        .first()
    )
    if endpoint is not None:
        return endpoint
    endpoint = ModelEndpoint(
        model_id=model.id,
        provider_id=provider.id,
        credential_id=credential.id,
        path="/chat/completions",
        method="POST",
        streaming_supported=True,
        enabled=True,
    )
    session.add(endpoint)
    report.endpoints += 1
    await session.flush()
    return endpoint


async def _ensure_routing_rule(
    session: AsyncSession, report: SeedReport, models: list[Model]
) -> RoutingRule:
    name = f"Chat default {DEMO_SUFFIX}"
    rule = (
        (await session.execute(select(RoutingRule).where(RoutingRule.name == name)))
        .scalars()
        .first()
    )
    if rule is not None:
        return rule
    rule = RoutingRule(
        name=name,
        strategy=RoutingStrategy.LATENCY_AWARE,
        match_conditions={"model": "gpt-4o-mini"},
        target_model_ids=[str(model.id) for model in models[:2]],
        fallback_chain=[str(model.id) for model in models],
        enabled=True,
    )
    session.add(rule)
    report.routing_rules += 1
    await session.flush()
    return rule


async def _ensure_api_key(session: AsyncSession, report: SeedReport) -> tuple[ApiKey, str]:
    existing = (
        (await session.execute(select(ApiKey).where(ApiKey.prefix.like(f"{DEMO_KEY_PREFIX}%"))))
        .scalars()
        .first()
    )
    if existing is not None:
        report.api_keys += 0
        return existing, f"{existing.prefix}… (unchanged: the secret is only shown once)"

    secret = f"{DEMO_KEY_PREFIX}_{uuid.uuid4().hex[:24]}"
    key = ApiKey(
        name=f"سرویس نمونه {DEMO_SUFFIX}",
        prefix=secret[:40],
        hash=ApiKey.hash_secret(secret) if hasattr(ApiKey, "hash_secret") else _hash(secret),
        scopes=list(KNOWN_SCOPES),
        rate_limit_per_min=60,
        quota_tokens=1_000_000,
        enabled=True,
    )
    session.add(key)
    report.api_keys += 1
    await session.flush()
    return key, secret


def _hash(secret: str) -> str:
    import hashlib

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


async def _ensure_health_check(
    session: AsyncSession, report: SeedReport, provider: Provider, now: datetime
) -> HealthCheck:
    existing = (
        (
            await session.execute(
                select(HealthCheck).where(
                    HealthCheck.provider_id == provider.id,
                    HealthCheck.status == HealthStatus.HEALTHY.value,
                )
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        provider.health_status = HealthStatus.HEALTHY.value
        return existing
    check = HealthCheck(
        target_type="provider",
        target_id=provider.id,
        provider_id=provider.id,
        status=HealthStatus.HEALTHY.value,
        latency_ms=180 if provider.priority == 1 else 640,
        status_code=200,
        checked_at=now - timedelta(minutes=4),
    )
    session.add(check)
    report.health_checks += 1
    provider.health_status = HealthStatus.HEALTHY.value
    await session.flush()
    return check


async def _ensure_traffic(
    session: AsyncSession,
    report: SeedReport,
    rng: random.Random,
    *,
    provider: Provider,
    credential: ProviderCredential,
    model: Model,
    api_key: ApiKey,
    days: int,
    per_day: int,
    now: datetime,
) -> None:
    """Deterministic demo traffic: mostly successes with a believable error share."""
    existing = (
        await session.execute(
            select(ClientRequest.id).where(ClientRequest.api_key_id == api_key.id).limit(1)
        )
    ).first()
    if existing is not None:
        report.notes.append("Demo traffic already present; usage rows were left untouched.")
        return

    for day in range(days):
        for index in range(per_day):
            created = (
                now
                - timedelta(days=day)
                - timedelta(hours=rng.randint(0, 23))
                - timedelta(minutes=index)
            )
            failed = rng.random() < 0.08
            tokens_in = rng.randint(80, 900)
            tokens_out = rng.randint(40, 500)
            latency = rng.randint(180, 2_400)
            request = ClientRequest(
                request_id=f"req-demo-{day}-{index}",
                api_key_id=api_key.id,
                requested_model=model.name,
                streaming=rng.random() < 0.25,
                state=(ClientRequestState.FAILED if failed else ClientRequestState.SUCCEEDED),
                attempt_count=2 if failed else 1,
                input_tokens=0 if failed else tokens_in,
                output_tokens=0 if failed else tokens_out,
                total_tokens=0 if failed else tokens_in + tokens_out,
                cost=Decimal("0")
                if failed
                else Decimal(str(round((tokens_in + tokens_out) * 0.000002, 8))),
                latency_ms=latency,
                final_status_code=503 if failed else 200,
                final_error_code="provider_unavailable" if failed else None,
                started_at=created,
                completed_at=created + timedelta(milliseconds=latency),
            )
            session.add(request)
            await session.flush()
            report.requests += 1

            attempts = 2 if failed else 1
            for number in range(1, attempts + 1):
                is_final = number == attempts
                session.add(
                    UsageRecord(
                        request_id=request.request_id,
                        client_request_id=request.id,
                        attempt_number=number,
                        is_final=is_final,
                        retryable=not is_final,
                        api_key_id=api_key.id,
                        provider_id=provider.id,
                        credential_id=credential.id,
                        model_id=model.id,
                        input_tokens=tokens_in if is_final and not failed else 0,
                        output_tokens=tokens_out if is_final and not failed else 0,
                        total_tokens=(tokens_in + tokens_out) if is_final and not failed else 0,
                        cost=(
                            Decimal("0")
                            if failed or not is_final
                            else Decimal(str(round((tokens_in + tokens_out) * 0.000002, 8)))
                        ),
                        latency_ms=latency if is_final else latency // 2,
                        status_code=200 if is_final and not failed else 503,
                        error_code=None if is_final and not failed else "provider_unavailable",
                        streaming=request.streaming,
                        created_at=created,
                    )
                )
                report.attempts += 1

    await session.flush()
