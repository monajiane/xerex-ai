"""Administrator management and server-side RBAC."""

from __future__ import annotations

from app.models.enums import AdminRole
from tests.conftest import OWNER_EMAIL, create_user, login


async def test_owner_can_create_and_list_users(client, session_factory, owner_headers) -> None:
    created = await client.post(
        "/api/v1/admin-users",
        headers=owner_headers,
        json={
            "email": "operator@xerex.ai",
            "password": "operator-password-1",
            "full_name": "Operator",
            "role": "operator",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "operator"

    listed = await client.get("/api/v1/admin-users", headers=owner_headers)
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 2
    assert body["page"] == 1
    emails = {item["email"] for item in body["items"]}
    assert emails == {OWNER_EMAIL, "operator@xerex.ai"}


async def test_duplicate_email_is_rejected(client, owner_headers) -> None:
    payload = {
        "email": OWNER_EMAIL,
        "password": "another-password-1",
        "role": "viewer",
    }
    response = await client.post("/api/v1/admin-users", headers=owner_headers, json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


async def test_viewer_cannot_manage_users(client, session_factory) -> None:
    await create_user(session_factory)
    await create_user(
        session_factory,
        email="viewer@xerex.ai",
        password="viewer-password-1",
        role=AdminRole.VIEWER,
    )
    viewer_token = await login(client, "viewer@xerex.ai", "viewer-password-1")
    viewer_headers = {"Authorization": f"Bearer {viewer_token}"}

    denied = await client.post(
        "/api/v1/admin-users",
        headers=viewer_headers,
        json={"email": "x@xerex.ai", "password": "whatever-pass-1", "role": "admin"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_role"

    allowed = await client.get("/api/v1/admin-users", headers=viewer_headers)
    assert allowed.status_code == 200


async def test_owner_cannot_be_downgraded(client, session_factory, owner_headers) -> None:
    owner = await create_user(
        session_factory, email="second.owner@xerex.ai", password="second-owner-pass-1"
    )
    downgrade = await client.patch(
        f"/api/v1/admin-users/{owner.id}",
        headers=owner_headers,
        json={"role": "viewer"},
    )
    assert downgrade.status_code == 422
    assert downgrade.json()["error"]["code"] == "owner_role_protected"


async def test_missing_user_returns_not_found_envelope(client, owner_headers) -> None:
    response = await client.patch(
        "/api/v1/admin-users/6f3f3a2e-0000-4000-8000-000000000000",
        headers=owner_headers,
        json={"role": "viewer"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert response.json()["error"]["request_id"]
