"""Health and liveness endpoints."""

from __future__ import annotations

import pytest


async def test_liveness_endpoint(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "Xerex AI"


async def test_health_reports_components(client) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    components = {component["name"]: component for component in body["components"]}
    assert components["database"]["status"] == "healthy"
    assert components["database"]["dialect"] == "sqlite"
    # Redis is unreachable in the test environment and must degrade, not fail.
    assert components["redis"]["status"] == "degraded"
    assert components["redis"]["degraded_ok"] is True
    assert body["status"] == "degraded"


async def test_request_id_header_is_echoed(client) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "req_test_123"})
    assert response.headers["X-Request-ID"] == "req_test_123"
    assert float(response.headers["X-Response-Time-ms"]) >= 0


@pytest.mark.parametrize("path", ["/api/v1/system/info"])
async def test_system_info_is_public(client, path: str) -> None:
    response = await client.get(path)
    assert response.status_code == 200
    body = response.json()
    assert body["localization"]["default_locale"] == "fa"
    assert body["localization"]["supported_locales"] == ["fa", "en"]
