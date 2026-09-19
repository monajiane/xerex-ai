"""System metadata, roadmap and reference catalogs."""

from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()


async def test_api_index_lists_implemented_modules(client, owner_headers) -> None:
    response = await client.get("/api/v1", headers=owner_headers)
    assert response.status_code == 200
    keys = {module["key"] for module in response.json()["modules"]}
    assert {"auth", "health", "dashboard", "admin_users", "settings", "audit_logs"} <= keys


async def test_roadmap_reports_only_implemented_modules(client, owner_headers) -> None:
    """The roadmap is the panel's honesty contract: nothing is claimed that is not built."""
    response = await client.get("/api/v1/system/roadmap", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["current_milestone"] == settings.milestone
    states = {module["key"]: module["state"] for module in body["modules"]}
    assert set(states) >= {
        "auth",
        "providers",
        "provider_credentials",
        "models",
        "api_keys",
        "gateway",
        "routing",
        "provider_health",
        "usage",
        "request_logs",
    }
    assert set(states.values()) == {"implemented"}

    providers = next(module for module in body["modules"] if module["key"] == "providers")
    assert any(endpoint["method"] == "POST" for endpoint in providers["endpoints"])
    usage = next(module for module in body["modules"] if module["key"] == "usage")
    assert {endpoint["path"] for endpoint in usage["endpoints"]} >= {
        "/api/v1/usage/summary",
        "/api/v1/usage/export",
    }
    logs = next(module for module in body["modules"] if module["key"] == "request_logs")
    assert any("{request_id}" in endpoint["path"] for endpoint in logs["endpoints"])


async def test_bootstrap_status_carries_the_milestone(client) -> None:
    """Pre-auth screens state the real milestone instead of a hard-coded value."""
    response = await client.get("/api/v1/auth/bootstrap-status")
    assert response.status_code == 200
    assert response.json()["milestone"] == settings.milestone


async def test_provider_catalog_is_metadata_only(client, owner_headers) -> None:
    response = await client.get("/api/v1/catalog/providers", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["implemented"] is True
    kinds = {item["kind"] for item in body["items"]}
    assert {"openai", "anthropic", "google", "deepseek", "qwen", "openai_compatible"} == kinds
    names = {item["display_name"] for item in body["items"]}
    assert {"OpenAI", "Claude", "Gemini", "DeepSeek", "Qwen"} <= names


async def test_routing_strategy_catalog(client, owner_headers) -> None:
    response = await client.get("/api/v1/catalog/routing-strategies", headers=owner_headers)
    body = response.json()
    strategies = {item["strategy"] for item in body["items"]}
    assert "latency_aware" in strategies
    assert "failover" in strategies
    # M5 implements every advertised strategy; the catalog says so rather than
    # pretending they are still planned.
    assert body["implemented"] is True
    assert all(item["implemented"] is True for item in body["items"])
    assert all(item["milestone"] == "M5" for item in body["items"])


async def test_unknown_route_uses_error_envelope(client) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "route_not_found"
