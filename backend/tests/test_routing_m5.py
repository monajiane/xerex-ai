"""Routing engine, rules and the dry-run simulator (M5).

Two layers are asserted separately, because they fail differently:

* the **engine** is pure — ordering, eligibility and the explanation tokens are tested
  without a database;
* the **service** adds observation (health/latency/price) and rule matching, so its
  tests check that a rule changes the order and that the simulator reports the same
  decision live traffic would take.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from app.models.enums import CredentialStatus, HealthStatus, RoutingStrategy
from app.models.health import HealthCheck
from app.models.routing import RoutingRule
from app.router.engine import CandidateScore, RoutingEngine
from app.services.routing import blended_price, rule_matches
from tests.conftest import create_user, login

PROVIDER_PRIMARY = {
    "name": "Primary",
    "kind": "openai",
    "base_url": "https://api.openai.com/v1",
    "priority": 1,
    "weight": 100,
}
PROVIDER_SECONDARY = {
    "name": "Secondary",
    "kind": "openai",
    "base_url": "https://api.openai.com/v1",
    "priority": 2,
    "weight": 50,
}


def _score(
    key: str,
    *,
    priority: int = 100,
    weight: int = 100,
    health: HealthStatus | None = HealthStatus.HEALTHY,
    latency: int | None = None,
    price: float | None = None,
) -> CandidateScore:
    return CandidateScore(
        key=key,
        score=0.0,
        health=health,
        latency_ms=latency,
        price_per_1m=price,
        payload={"priority": priority, "weight": weight},
    )


def _order(candidates: list[CandidateScore], strategy: RoutingStrategy, offset: int = 0):
    decision = RoutingEngine().rank(candidates, strategy, offset=offset)
    return [item.key for item in decision.ordered if item.eligible]


# --------------------------------------------------------------------------- #
# Engine (pure)
# --------------------------------------------------------------------------- #
def test_priority_strategy_prefers_the_lowest_priority_number() -> None:
    candidates = [_score("b", priority=5), _score("a", priority=1), _score("c", priority=9)]
    assert _order(candidates, RoutingStrategy.PRIORITY) == ["a", "b", "c"]


def test_priority_strategy_is_deterministic_for_equal_priorities() -> None:
    first = _order([_score("z", priority=3), _score("a", priority=3)], RoutingStrategy.PRIORITY)
    second = _order([_score("a", priority=3), _score("z", priority=3)], RoutingStrategy.PRIORITY)
    assert first == second == ["a", "z"]


def test_weighted_strategy_prefers_the_highest_weight() -> None:
    candidates = [_score("low", weight=10), _score("high", weight=90)]
    assert _order(candidates, RoutingStrategy.WEIGHTED) == ["high", "low"]


def test_latency_aware_puts_unmeasured_candidates_after_measured_ones() -> None:
    candidates = [_score("unknown"), _score("slow", latency=900), _score("fast", latency=120)]
    assert _order(candidates, RoutingStrategy.LATENCY_AWARE) == ["fast", "slow", "unknown"]


def test_cost_aware_orders_by_blended_price_and_marks_missing_prices() -> None:
    candidates = [_score("priceless"), _score("cheap", price=3), _score("pricey", price=30)]
    decision = RoutingEngine().rank(candidates, RoutingStrategy.COST_AWARE)
    eligible = [item.key for item in decision.ordered if item.eligible]
    assert eligible == ["cheap", "pricey", "priceless"]
    priceless = next(item for item in decision.candidates if item.key == "priceless")
    assert "no_price_data" in priceless.reasons


def test_failover_skips_down_candidates_and_explains_why() -> None:
    candidates = [
        _score("down", priority=1, health=HealthStatus.DOWN),
        _score("degraded", priority=2, health=HealthStatus.DEGRADED),
        _score("healthy", priority=3, health=HealthStatus.HEALTHY),
    ]
    decision = RoutingEngine().rank(candidates, RoutingStrategy.FAILOVER)
    ordered = [item.key for item in decision.ordered]
    assert ordered == ["healthy", "degraded", "down"]  # down is still last, not dropped
    down = next(item for item in decision.candidates if item.key == "down")
    assert down.eligible is False
    assert "excluded_health_down" in down.reasons
    assert "health=down" in down.reasons


def test_rate_limited_candidate_stays_eligible_but_ranks_last() -> None:
    candidates = [
        _score("limited", priority=1, health=HealthStatus.RATE_LIMITED),
        _score("healthy", priority=5, health=HealthStatus.HEALTHY),
    ]
    decision = RoutingEngine().rank(candidates, RoutingStrategy.FAILOVER)
    assert [item.key for item in decision.ordered] == ["healthy", "limited"]
    assert all(item.eligible for item in decision.candidates)


def test_round_robin_rotates_with_the_offset() -> None:
    def make() -> list[CandidateScore]:
        return [_score("a", priority=1), _score("b", priority=2), _score("c", priority=3)]

    assert _order(make(), RoutingStrategy.ROUND_ROBIN, offset=0) == ["a", "b", "c"]
    assert _order(make(), RoutingStrategy.ROUND_ROBIN, offset=1) == ["b", "c", "a"]
    assert _order(make(), RoutingStrategy.ROUND_ROBIN, offset=2) == ["c", "a", "b"]
    assert _order(make(), RoutingStrategy.ROUND_ROBIN, offset=3) == ["a", "b", "c"]


def test_every_advertised_strategy_is_implemented() -> None:
    from app.router.engine import catalog

    assert catalog()
    assert all(item["implemented"] is True for item in catalog())
    assert {item["strategy"] for item in catalog()} == {s.value for s in RoutingStrategy}


def test_blended_price_sums_input_and_output_prices() -> None:
    class _Model:
        input_price_per_1m = 3
        output_price_per_1m = 15

    class _Unknown:
        input_price_per_1m = None
        output_price_per_1m = None

    assert blended_price(_Model()) == 18
    assert blended_price(_Unknown()) is None


def test_rule_matching_uses_ids_patterns_or_everything() -> None:
    import uuid

    model_id = uuid.uuid4()
    everything = RoutingRule(name="all", match_conditions={}, target_model_ids=[])
    by_id = RoutingRule(name="by-id", match_conditions={}, target_model_ids=[str(model_id)])
    by_pattern = RoutingRule(name="pattern", match_conditions={"model": "gpt-4o*"})

    assert rule_matches(everything, model_name="anything", model_id=uuid.uuid4()) is True
    assert rule_matches(by_id, model_name="x", model_id=model_id) is True
    assert rule_matches(by_id, model_name="x", model_id=uuid.uuid4()) is False
    assert rule_matches(by_pattern, model_name="gpt-4o-mini", model_id=uuid.uuid4()) is True
    assert rule_matches(by_pattern, model_name="claude-3", model_id=uuid.uuid4()) is False


# --------------------------------------------------------------------------- #
# API fixtures
# --------------------------------------------------------------------------- #
async def _headers(client, session_factory) -> dict[str, str]:
    await create_user(session_factory)
    return {"Authorization": f"Bearer {await login(client)}"}


async def _provider(client, headers, payload: dict, secret: str = "sk-live-abcdefghijklmnop"):
    provider = (await client.post("/api/v1/providers", json=payload, headers=headers)).json()
    await client.post(
        f"/api/v1/providers/{provider['id']}/credentials",
        json={"label": "primary", "secret": secret},
        headers=headers,
    )
    return provider


async def _model(client, headers, provider, name: str = "gpt-4o-mini", **prices):
    body = {"provider_id": provider["id"], "name": name, **prices}
    response = await client.post("/api/v1/models", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def _ok_probe(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}]})
    return httpx.Response(404, json={"error": {"message": "not found"}})


def _install_probe(monkeypatch, handler=_ok_probe) -> None:
    import app.services.health_admin as module

    real_build = module.build_adapter

    def fake_build(*, kind, base_url, secret, timeout_ms=30_000, client=None):  # noqa: ANN001
        return real_build(
            kind=kind,
            base_url=base_url,
            secret=secret,
            timeout_ms=timeout_ms,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(module, "build_adapter", fake_build)


# --------------------------------------------------------------------------- #
# Rules API
# --------------------------------------------------------------------------- #
async def test_rules_crud_is_audited_and_name_unique(client, session_factory, session) -> None:
    headers = await _headers(client, session_factory)

    created = await client.post(
        "/api/v1/routing/rules",
        json={"name": "چت پشتیبانی", "strategy": "latency_aware", "priority": 10},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["strategy"] == "latency_aware"
    assert rule["enabled"] is True

    duplicate = await client.post(
        "/api/v1/routing/rules", json={"name": "چت پشتیبانی"}, headers=headers
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "routing_rule_name_taken"

    updated = await client.patch(
        f"/api/v1/routing/rules/{rule['id']}",
        json={"enabled": False, "priority": 5, "match_conditions": {"model": "gpt-4o*"}},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["match_conditions"] == {"model": "gpt-4o*"}

    invalid = await client.patch(
        f"/api/v1/routing/rules/{rule['id']}",
        json={"match_conditions": {"country": "ir"}},
        headers=headers,
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "routing_conditions_invalid"

    listed = await client.get("/api/v1/routing/rules", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await client.delete(f"/api/v1/routing/rules/{rule['id']}", headers=headers)
    assert deleted.status_code == 200

    logs = (await client.get("/api/v1/audit-logs?page_size=50", headers=headers)).json()
    actions = {entry["action"] for entry in logs["items"]}
    assert {"routing_rule_created", "routing_rule_updated", "routing_rule_deleted"} <= actions
    stored = (await session.execute(select(RoutingRule))).scalars().all()
    assert stored == []


async def test_rule_creation_requires_the_write_role(client, session_factory) -> None:
    from app.models.enums import AdminRole

    await create_user(session_factory)
    owner_headers = {"Authorization": f"Bearer {await login(client)}"}
    assert (
        await client.post("/api/v1/routing/rules", json={"name": "ok"}, headers=owner_headers)
    ).status_code == 201

    await create_user(session_factory, email="viewer@xerex.ai", role=AdminRole.VIEWER)
    viewer_headers = {"Authorization": f"Bearer {await login(client, 'viewer@xerex.ai')}"}
    assert (await client.get("/api/v1/routing/rules", headers=viewer_headers)).status_code == 200
    denied = await client.post(
        "/api/v1/routing/rules", json={"name": "nope"}, headers=viewer_headers
    )
    assert denied.status_code == 403


# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
async def test_simulation_ranks_candidates_with_reasons(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    primary = await _provider(client, headers, PROVIDER_PRIMARY)
    secondary = await _provider(client, headers, PROVIDER_SECONDARY)
    await _model(client, headers, primary, input_price_per_1m=3, output_price_per_1m=15)
    await _model(client, headers, secondary, input_price_per_1m=1, output_price_per_1m=5)

    response = await client.post(
        "/api/v1/routing/simulate",
        json={"model": "gpt-4o-mini", "strategy": "cost_aware", "requested_tokens": 1000},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["strategy"] == "cost_aware"
    assert [row["provider_name"] for row in body["candidates"]] == ["Secondary", "Primary"]
    assert body["selected_provider_id"] == secondary["id"]
    cheapest = body["candidates"][0]
    assert cheapest["price_per_1m"] == 6
    assert cheapest["estimated_cost"] == pytest.approx(0.006, abs=1e-9)
    assert any(reason.startswith("blended_price=") for reason in cheapest["reasons"])
    assert "candidates=2" in body["explanation"]


async def test_simulation_uses_the_matching_rule_strategy(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider(client, headers, PROVIDER_PRIMARY)
    await _model(client, headers, provider)

    await client.post(
        "/api/v1/routing/rules",
        json={
            "name": "فقط gpt",
            "strategy": "round_robin",
            "match_conditions": {"model": "gpt-4o*"},
            "priority": 1,
        },
        headers=headers,
    )

    response = await client.post(
        "/api/v1/routing/simulate", json={"model": "gpt-4o-mini"}, headers=headers
    )
    body = response.json()
    assert body["strategy"] == "round_robin"
    assert body["rule_name"] == "فقط gpt"
    assert any(entry.startswith("rule=") for entry in body["explanation"])

    # A model that does not match the pattern keeps the default strategy.
    other = await client.post(
        "/api/v1/routing/simulate", json={"model": "unknown-model"}, headers=headers
    )
    assert other.json()["strategy"] == "priority"
    assert other.json()["candidates"] == []
    assert "no_candidate" in other.json()["explanation"]


async def test_simulation_excludes_a_provider_whose_health_is_down(
    client, session_factory, session
) -> None:
    from datetime import UTC, datetime

    headers = await _headers(client, session_factory)
    primary = await _provider(client, headers, PROVIDER_PRIMARY)
    secondary = await _provider(client, headers, PROVIDER_SECONDARY)
    await _model(client, headers, primary)
    await _model(client, headers, secondary)

    session.add(
        HealthCheck(
            target_type="provider",
            target_id=__import__("uuid").UUID(primary["id"]),
            provider_id=__import__("uuid").UUID(primary["id"]),
            status=HealthStatus.DOWN,
            latency_ms=None,
            error_code="provider_unavailable",
            checked_at=datetime.now(UTC),
        )
    )
    await session.commit()

    response = await client.post(
        "/api/v1/routing/simulate",
        json={"model": "gpt-4o-mini", "strategy": "failover"},
        headers=headers,
    )
    body = response.json()
    assert body["selected_provider_id"] == secondary["id"]
    down = next(row for row in body["candidates"] if row["provider_id"] == primary["id"])
    assert down["eligible"] is False
    assert "excluded_health_down" in down["reasons"]


async def test_simulation_requires_a_model(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    response = await client.post("/api/v1/routing/simulate", json={}, headers=headers)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "routing_simulation_model_required"


# --------------------------------------------------------------------------- #
# Health checks
# --------------------------------------------------------------------------- #
async def test_health_overview_reports_unknown_before_any_check(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider(client, headers, PROVIDER_PRIMARY)

    response = await client.get("/api/v1/health/providers", headers=headers)
    assert response.status_code == 200
    row = next(item for item in response.json() if item["provider_id"] == provider["id"])
    assert row["status"] == "unknown"
    assert row["last_checked_at"] is None
    assert row["uptime_percent"] is None
    assert row["requests"] == 0


async def test_running_checks_records_observations_and_audit(
    client, session_factory, session, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider(client, headers, PROVIDER_PRIMARY)
    _install_probe(monkeypatch)

    response = await client.post("/api/v1/health/checks", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["checked"] == 1
    assert body["statuses"] == {"healthy": 1}
    assert body["failures"] == []

    observations = (
        (await session.execute(select(HealthCheck).order_by(HealthCheck.checked_at)))
        .scalars()
        .all()
    )
    kinds = {row.target_type.value for row in observations}
    assert {"provider", "credential"} <= kinds
    assert {row.status for row in observations} == {HealthStatus.HEALTHY}

    overview = (await client.get("/api/v1/health/providers", headers=headers)).json()
    row = next(item for item in overview if item["provider_id"] == provider["id"])
    assert row["status"] == "healthy"
    assert row["last_checked_at"] is not None
    assert row["uptime_percent"] == 100.0

    history = (await client.get("/api/v1/health/observations?limit=10", headers=headers)).json()
    assert history
    assert history[0]["status"] in {"healthy", "degraded", "rate_limited", "down", "unknown"}
    assert history[0]["checked_at"]

    logs = (await client.get("/api/v1/audit-logs?page_size=20", headers=headers)).json()
    run = next(entry for entry in logs["items"] if entry["action"] == "health_checks_run")
    assert run["diff"]["checked"] == 1


async def test_failed_check_marks_the_provider_and_keeps_the_error_code(
    client, session_factory, session, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider(client, headers, PROVIDER_PRIMARY)

    def unauthorised(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    _install_probe(monkeypatch, unauthorised)
    response = await client.post("/api/v1/health/checks", headers=headers)
    body = response.json()
    assert body["statuses"] == {"down": 1}
    assert body["failures"][0]["error_code"] == "provider_unauthorized"

    observations = (await session.execute(select(HealthCheck))).scalars().all()
    assert {row.status for row in observations} == {HealthStatus.DOWN}

    stored = await session.get(
        __import__("app.models.providers", fromlist=["Provider"]).Provider,
        __import__("uuid").UUID(provider["id"]),
    )
    assert stored is not None
    assert stored.health_status == "down"

    credentials = (
        await client.get(f"/api/v1/providers/{provider['id']}/credentials", headers=headers)
    ).json()
    assert credentials["items"][0]["status"] != CredentialStatus.ACTIVE.value


async def test_provider_without_credential_is_reported_honestly(
    client, session_factory, session, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    provider = (
        await client.post("/api/v1/providers", json=PROVIDER_PRIMARY, headers=headers)
    ).json()
    _install_probe(monkeypatch)

    body = (await client.post("/api/v1/health/checks", headers=headers)).json()
    assert body["statuses"] == {"unknown": 1}
    assert body["failures"][0]["error_code"] == "credential_missing"

    overview = (await client.get("/api/v1/health/providers", headers=headers)).json()
    row = next(item for item in overview if item["provider_id"] == provider["id"])
    assert row["status"] == "unknown"


async def test_viewer_may_not_run_checks(client, session_factory, monkeypatch) -> None:
    from app.models.enums import AdminRole

    await create_user(session_factory)
    owner_headers = {"Authorization": f"Bearer {await login(client)}"}
    await create_user(session_factory, email="viewer@xerex.ai", role=AdminRole.VIEWER)
    viewer_headers = {"Authorization": f"Bearer {await login(client, 'viewer@xerex.ai')}"}

    denied = await client.post("/api/v1/health/checks", headers=viewer_headers)
    assert denied.status_code == 403
    assert (await client.get("/api/v1/health/providers", headers=viewer_headers)).status_code == 200
    assert owner_headers
