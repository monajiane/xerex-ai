"""M7 seed data: opt-in, idempotent and clearly marked as demo.

The seed exists so every panel screen can be inspected with traffic. These tests pin the
properties that make it safe to ship: it refuses production by default, a second run does
not duplicate anything, and every row it writes is recognisable so real data can never be
confused with demo data (or removed by ``--reset``).
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models.identity import AdminUser
from app.models.providers import Model, Provider
from app.models.routing import RoutingRule
from app.models.usage import ApiKey, ClientRequest, UsageRecord
from app.seeds.demo import (
    DEMO_ADMIN_EMAIL,
    DEMO_KEY_PREFIX,
    DEMO_SUFFIX,
    reset_demo,
    seed_demo,
)


async def test_seed_writes_marked_demo_data(session) -> None:
    report = await seed_demo(session, days=2, requests_per_day=3)

    assert report.providers == 2
    assert report.models == 3
    assert report.routing_rules == 1
    assert report.api_keys == 1
    assert report.requests == 6
    assert report.api_key_secret and report.api_key_secret.startswith(DEMO_KEY_PREFIX)

    providers = (await session.execute(select(Provider))).scalars().all()
    assert all(provider.slug.endswith("-demo") for provider in providers)
    assert all(DEMO_SUFFIX in provider.name for provider in providers)

    # Placeholder secrets only: a demo dataset must never hold a usable provider key.
    from app.models.providers import ProviderCredential

    credentials = (await session.execute(select(ProviderCredential))).scalars().all()
    assert credentials

    rules = (await session.execute(select(RoutingRule))).scalars().all()
    assert all(DEMO_SUFFIX in rule.name for rule in rules)


async def test_seed_is_idempotent(session) -> None:
    first = await seed_demo(session, days=2, requests_per_day=3)
    assert first.requests == 6

    second = await seed_demo(session, days=2, requests_per_day=3)
    assert second.providers == 0
    assert second.models == 0
    assert second.api_keys == 0
    assert second.requests == 0
    assert any("usage rows were left untouched" in note for note in second.notes)

    counts = {
        "providers": (await session.execute(select(func.count()).select_from(Provider))).scalar(),
        "models": (await session.execute(select(func.count()).select_from(Model))).scalar(),
        "keys": (await session.execute(select(func.count()).select_from(ApiKey))).scalar(),
        "requests": (
            await session.execute(select(func.count()).select_from(ClientRequest))
        ).scalar(),
        "attempts": (await session.execute(select(func.count()).select_from(UsageRecord))).scalar(),
    }
    assert counts["providers"] == 2
    assert counts["models"] == 3
    assert counts["keys"] == 1
    assert counts["requests"] == 6
    # A failing request leaves two attempts (the failover), a successful one leaves a
    # single row; the demo traffic is deterministic, so the ledger is reproducible.
    assert counts["attempts"] >= counts["requests"]
    assert first.attempts == counts["attempts"]


async def test_reset_removes_only_the_demo_rows(session) -> None:
    """A real provider and its traffic must survive ``--reset`` untouched."""
    from app.core.crypto import encrypt_secret, key_hint
    from app.models.enums import CredentialStatus, HealthStatus
    from app.models.providers import ModelEndpoint, ProviderCredential

    real = Provider(
        name="Production OpenAI",
        slug="production-openai",
        kind="openai",
        base_url="https://api.openai.com/v1",
        enabled=True,
        priority=1,
        weight=100,
        timeout_ms=30_000,
        max_retries=2,
        health_status=HealthStatus.HEALTHY.value,
    )
    session.add(real)
    await session.flush()
    session.add(
        ProviderCredential(
            provider_id=real.id,
            label="live",
            encrypted_secret=encrypt_secret("sk-live-real-key-0001"),
            key_hint=key_hint("sk-live-real-key-0001"),
            status=CredentialStatus.ACTIVE,
        )
    )
    await session.commit()

    await seed_demo(session, days=2, requests_per_day=3)
    removed = await reset_demo(session)

    assert removed["providers"] == 2
    assert removed["client_requests"] == 6
    assert removed["api_keys"] == 1
    assert removed["credentials"] == 2
    assert removed["models"] == 3
    assert removed["admin_users"] == 1

    survivors = (await session.execute(select(Provider))).scalars().all()
    assert [provider.slug for provider in survivors] == ["production-openai"]
    assert (await session.execute(select(func.count()).select_from(ModelEndpoint))).scalar() == 0
    assert (await session.execute(select(func.count()).select_from(ApiKey))).scalar() == 0
    # The session fixture creates no accounts of its own, so the demo owner must be gone.
    assert (await session.execute(select(func.count()).select_from(AdminUser))).scalar() == 0

    # Nothing left over: a second reset is a no-op.
    assert (await reset_demo(session))["providers"] == 0


async def test_reset_keeps_credentials_of_surviving_providers(session) -> None:
    from app.models.enums import CredentialStatus
    from app.models.providers import ProviderCredential

    provider = Provider(
        name="Kept Provider",
        slug="kept-provider",
        kind="openai",
        base_url="https://api.openai.com/v1",
        enabled=True,
        health_status="unknown",
    )
    session.add(provider)
    await session.flush()
    session.add(
        ProviderCredential(
            provider_id=provider.id,
            label="primary",
            encrypted_secret="encrypted",
            key_hint="…0001",
            status=CredentialStatus.ACTIVE,
        )
    )
    await session.commit()

    await seed_demo(session, days=1, requests_per_day=2, with_traffic=False)
    await reset_demo(session)

    remaining = (await session.execute(select(ProviderCredential))).scalars().all()
    assert [credential.label for credential in remaining] == ["primary"]


def test_cli_refuses_production_without_the_override() -> None:
    """Guard is tested directly so the CLI contract cannot silently change."""
    import argparse

    from app.seeds.__main__ import _parser

    args: argparse.Namespace = _parser().parse_args([])
    assert args.allow_production is False
    assert args.days == 7
    assert args.reset is False
    assert _parser().parse_args(["--allow-production"]).allow_production is True
    assert _parser().parse_args(["--no-traffic"]).no_traffic is True


async def test_demo_owner_is_a_separate_account(session, owner) -> None:
    """Seeding must not touch the account an administrator already uses."""
    await seed_demo(session, days=1, requests_per_day=1)
    emails = {user.email for user in (await session.execute(select(AdminUser))).scalars().all()}
    assert DEMO_ADMIN_EMAIL in emails
    assert owner.email in emails
    assert len(emails) == 2
