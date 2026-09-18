"""Platform settings, audit trail and dashboard aggregates."""

from __future__ import annotations

from app.models.enums import AdminRole
from tests.conftest import login


async def test_settings_bundle_exposes_persian_first_defaults(client, owner_headers) -> None:
    response = await client.get("/api/v1/settings", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["default_locale"] == "fa"
    values = {item["key"]: item["value"] for item in body["items"]}
    assert values["ui.default_locale"] == "fa"
    assert values["ui.numeral_style"] == "persian"


async def test_setting_update_is_validated_and_audited(client, owner_headers) -> None:
    updated = await client.put(
        "/api/v1/settings/ui.numeral_style", headers=owner_headers, json={"value": "latin"}
    )
    assert updated.status_code == 200
    assert updated.json()["value"] == "latin"

    rejected = await client.put(
        "/api/v1/settings/ui.numeral_style", headers=owner_headers, json={"value": "roman"}
    )
    assert rejected.status_code == 422

    unknown = await client.put(
        "/api/v1/settings/does.not.exist", headers=owner_headers, json={"value": 1}
    )
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_setting"

    audit = await client.get("/api/v1/audit-logs", headers=owner_headers)
    actions = {entry["action"] for entry in audit.json()["items"]}
    assert "settings_updated" in actions


async def test_audit_trail_records_logins(client, session_factory) -> None:
    from tests.conftest import OWNER_EMAIL, create_user

    await create_user(session_factory)
    token = await login(client)
    headers = {"Authorization": f"Bearer {token}"}

    failed = await client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "nope-nope-nope"}
    )
    assert failed.status_code == 401

    response = await client.get("/api/v1/audit-logs", headers=headers)
    assert response.status_code == 200
    actions = [entry["action"] for entry in response.json()["items"]]
    assert "login_succeeded" in actions
    assert "login_failed" in actions
    assert all(entry["request_id"] for entry in response.json()["items"])


async def test_audit_logs_require_elevated_role(client, session_factory) -> None:
    from tests.conftest import create_user

    await create_user(session_factory)
    await create_user(
        session_factory,
        email="auditor-viewer@xerex.ai",
        password="viewer-password-1",
        role=AdminRole.VIEWER,
    )
    token = await login(client, "auditor-viewer@xerex.ai", "viewer-password-1")
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/v1/audit-logs", headers=headers)
    assert response.status_code == 403


async def test_dashboard_summary_is_honest_about_empty_platform(client, owner_headers) -> None:
    response = await client.get("/api/v1/dashboard/summary", headers=owner_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["has_provider_data"] is False
    assert body["provider_health"] == []
    assert body["counts"]["providers"] == 0
    assert body["counts"]["admin_users"] >= 1
    metrics = {metric["key"]: metric for metric in body["metrics"]}
    assert metrics["requests"]["value"] == 0
    assert metrics["p95_latency_ms"]["available"] is False
    assert metrics["error_rate"]["available"] is False
