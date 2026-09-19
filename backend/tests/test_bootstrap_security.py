"""First-run bootstrap gating (correction pass item 1).

Acceptance criteria:

* bootstrap only works while zero administrators exist;
* ``XEREX_BOOTSTRAP_ENABLED`` explicitly controls it;
* production does not silently default to enabled.
"""

from __future__ import annotations

from app.core.config import get_settings

settings = get_settings()

from app.core.config import Settings
from app.core.config import settings as runtime_settings
from app.models.enums import AdminRole
from tests.conftest import create_user

BOOTSTRAP_PAYLOAD = {
    "email": "first.owner@xerex.ai",
    "password": "a-very-strong-password",
    "full_name": "First Owner",
}


async def test_bootstrap_status_reports_that_setup_is_allowed(client) -> None:
    response = await client.get("/api/v1/auth/bootstrap-status")
    body = response.json()
    assert body == {
        "requires_bootstrap": True,
        "bootstrap_enabled": True,
        "admin_user_count": 0,
        "bootstrap_allowed": True,
        # Reported so the pre-auth footer states the real milestone.
        "milestone": settings.milestone,
    }


async def test_bootstrap_is_disabled_when_the_flag_is_false(client, monkeypatch) -> None:
    monkeypatch.setattr(runtime_settings, "bootstrap_enabled", False)

    status = await client.get("/api/v1/auth/bootstrap-status")
    body = status.json()
    assert body["bootstrap_enabled"] is False
    assert body["bootstrap_allowed"] is False
    assert body["requires_bootstrap"] is True  # still no owner, but setup is off

    response = await client.post("/api/v1/auth/bootstrap", json=BOOTSTRAP_PAYLOAD)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "bootstrap_disabled"


async def test_bootstrap_becomes_unavailable_after_the_first_owner(client) -> None:
    created = await client.post("/api/v1/auth/bootstrap", json=BOOTSTRAP_PAYLOAD)
    assert created.status_code == 201

    status = await client.get("/api/v1/auth/bootstrap-status")
    body = status.json()
    assert body["admin_user_count"] == 1
    assert body["requires_bootstrap"] is False
    assert body["bootstrap_allowed"] is False

    again = await client.post("/api/v1/auth/bootstrap", json=BOOTSTRAP_PAYLOAD)
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "bootstrap_closed"


async def test_bootstrap_is_closed_when_an_administrator_already_exists(
    client, session_factory
) -> None:
    await create_user(session_factory, role=AdminRole.VIEWER)

    response = await client.post("/api/v1/auth/bootstrap", json=BOOTSTRAP_PAYLOAD)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "bootstrap_closed"


def test_production_default_is_disabled_and_development_default_is_enabled() -> None:
    import base64

    key = base64.urlsafe_b64encode(bytes(range(32))).decode()
    production = Settings(
        _env_file=None,
        environment="production",
        secret_key="n7Qv2Lx9pR4tYb8Kd3Ws6Jm1Zc5Hg0UaEfTnIoPqBrSvWxyCz",
        credentials_encryption_key=key,
        debug=False,
        bootstrap_enabled=None,
    )
    assert production.bootstrap_enabled_effective is False
    assert Settings(_env_file=None, environment="development").bootstrap_enabled_effective is True
