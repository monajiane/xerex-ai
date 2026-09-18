"""Authentication flows: bootstrap, login, refresh rotation, logout."""

from __future__ import annotations

from app.core.errors import AuthenticationError
from app.core.security import create_access_token, decode_token
from tests.conftest import OWNER_EMAIL, OWNER_PASSWORD, create_user


async def test_bootstrap_status_before_and_after(client, session_factory) -> None:
    response = await client.get("/api/v1/auth/bootstrap-status")
    assert response.json()["requires_bootstrap"] is True

    await create_user(session_factory)

    response = await client.get("/api/v1/auth/bootstrap-status")
    assert response.json()["requires_bootstrap"] is False
    assert response.json()["admin_user_count"] == 1


async def test_bootstrap_creates_owner_and_closes_itself(client) -> None:
    payload = {
        "email": "first.owner@xerex.ai",
        "password": "a-very-strong-password",
        "full_name": "First Owner",
    }
    response = await client.post("/api/v1/auth/bootstrap", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["role"] == "owner"
    assert body["tokens"]["access_token"]
    assert client.cookies.get("xerex_refresh_token")

    again = await client.post("/api/v1/auth/bootstrap", json=payload)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "bootstrap_closed"


async def test_bootstrap_rejects_short_password(client) -> None:
    response = await client.post(
        "/api/v1/auth/bootstrap",
        json={"email": "short@xerex.ai", "password": "too-short"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_failed"


async def test_login_with_valid_and_invalid_credentials(client, session_factory) -> None:
    await create_user(session_factory)

    ok = await client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    assert ok.status_code == 200
    assert ok.json()["user"]["email"] == OWNER_EMAIL

    bad = await client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "wrong-password"}
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"


async def test_me_requires_a_token(client, session_factory, owner_headers) -> None:
    anonymous = await client.get("/api/v1/auth/me")
    assert anonymous.status_code == 401
    assert anonymous.json()["error"]["code"] == "authentication_required"

    response = await client.get("/api/v1/auth/me", headers=owner_headers)
    assert response.status_code == 200
    assert response.json()["email"] == OWNER_EMAIL


async def test_refresh_rotates_the_token(client, session_factory) -> None:
    await create_user(session_factory)
    await client.post("/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
    first_cookie = client.cookies.get("xerex_refresh_token")

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200, refreshed.text
    second_cookie = client.cookies.get("xerex_refresh_token")
    assert second_cookie and second_cookie != first_cookie

    # The rotated token is single use.
    replay = await client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"xerex_refresh_token={first_cookie}"}
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "token_revoked"


async def test_logout_revokes_the_session(client, session_factory) -> None:
    await create_user(session_factory)
    login = await client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
    )
    token = login.json()["tokens"]["access_token"]

    response = await client.post(
        "/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "logged_out"

    refreshed = await client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 401


async def test_inactive_account_cannot_login(client, session_factory) -> None:
    from app.models.enums import AdminRole, UserStatus

    await create_user(
        session_factory,
        email="suspended@xerex.ai",
        role=AdminRole.OPERATOR,
        status=UserStatus.SUSPENDED,
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": "suspended@xerex.ai", "password": OWNER_PASSWORD}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "account_inactive"


async def test_access_token_type_is_enforced(client, session_factory) -> None:
    user = await create_user(session_factory)
    refresh_like = create_access_token(str(user.id), role="owner", email=user.email)

    # A token signed for another audience/type must not be accepted as a refresh token.
    try:
        decode_token(refresh_like.token, expected_type="refresh")
    except AuthenticationError as exc:
        assert exc.code == "token_type_invalid"
    else:  # pragma: no cover - defensive
        raise AssertionError("access token accepted as refresh token")
