"""System metadata, roadmap and reference catalogs."""

from __future__ import annotations


async def test_api_index_lists_implemented_modules(client, owner_headers) -> None:
    response = await client.get("/api/v1", headers=owner_headers)
    assert response.status_code == 200
    keys = {module["key"] for module in response.json()["modules"]}
    assert {"auth", "health", "dashboard", "admin_users", "settings", "audit_logs"} <= keys


async def test_roadmap_marks_planned_modules(client, owner_headers) -> None:
    response = await client.get("/api/v1/system/roadmap", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["current_milestone"] == "M1"
    states = {module["key"]: module["state"] for module in body["modules"]}
    assert states["providers"] == "planned"
    assert states["models"] == "planned"
    assert states["routing"] == "planned"
    assert states["auth"] == "implemented"

    providers = next(module for module in body["modules"] if module["key"] == "providers")
    assert any(endpoint["method"] == "POST" for endpoint in providers["endpoints"])


async def test_provider_catalog_is_metadata_only(client, owner_headers) -> None:
    response = await client.get("/api/v1/catalog/providers", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["implemented"] is False
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
    assert all(item["implemented"] is False for item in body["items"])


async def test_unknown_route_uses_error_envelope(client) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "route_not_found"
