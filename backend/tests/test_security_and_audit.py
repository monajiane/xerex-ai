"""Security-sensitive behaviour that must not regress (correction pass item 11).

Covered here:

* provider secrets are never returned by the API contract;
* secrets passed to the logger or to the audit trail are redacted;
* API keys, refresh tokens and passwords are stored in non-reversible form;
* RBAC stays server-side and an administrator cannot escalate their own role.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select

from app.core.logging import JsonFormatter
from app.core.security import generate_api_key, hash_api_key, hash_password
from app.models.audit import AuditLog
from app.models.enums import AdminRole
from app.models.identity import RefreshToken
from app.schemas.providers import CredentialRead
from app.services.audit import AuditService
from tests.conftest import OWNER_EMAIL, create_user, login


# --------------------------------------------------------------------------- #
# Secrets never leave the API
# --------------------------------------------------------------------------- #
def test_credential_read_contract_has_no_secret_fields() -> None:
    fields = set(CredentialRead.model_fields)
    assert {"encrypted_secret", "secret", "plaintext", "ciphertext"} & fields == set()
    assert "key_hint" in fields  # the masked hint is intentional


def test_credential_read_serialisation_never_contains_the_ciphertext() -> None:
    class Row:
        id = "8f2a1c2e-0000-4000-8000-000000000001"
        provider_id = "8f2a1c2e-0000-4000-8000-000000000002"
        label = "Primary"
        status = "active"
        key_hint = "…a91f"
        last_verified_at = None
        last_error_code = None
        created_at = datetime(2026, 9, 18)

    payload = CredentialRead.model_validate(Row(), from_attributes=True).model_dump()
    assert "encrypted_secret" not in payload
    assert "sk-live-super-secret" not in str(payload)


# --------------------------------------------------------------------------- #
# Redaction in logs and audit storage
# --------------------------------------------------------------------------- #
def test_json_logs_redact_secret_extras() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="xerex.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="provider_created",
        args=(),
        exc_info=None,
    )
    record.api_key = "xrx_live_8f2a_super_secret_value"
    record.provider_secret = "sk-live-1234567890"
    record.provider_slug = "openai"  # not sensitive, must survive
    formatted = formatter.format(record)
    assert "xrx_live_8f2a_super_secret_value" not in formatted
    assert "sk-live-1234567890" not in formatted
    assert "[redacted]" in formatted
    assert "openai" in formatted


async def test_audit_diff_is_redacted_before_storage(session_factory) -> None:
    async with session_factory() as session:
        await AuditService(session).record(
            "settings_updated",  # type: ignore[arg-type]
            diff={
                "provider_secret": "sk-live-1234567890",
                "nested": {"api_key": "xrx_live_8f2a", "credential_id": "keep-me"},
                "locale": "fa",
            },
        )
        await session.commit()

        entry = (await session.execute(select(AuditLog).limit(1))).scalar_one()

    assert entry.diff["provider_secret"] == "[redacted]"
    assert entry.diff["nested"]["api_key"] == "[redacted]"
    assert entry.diff["nested"]["credential_id"] == "keep-me"  # identifier, not a secret
    assert entry.diff["locale"] == "fa"
    assert "sk-live-1234567890" not in str(entry.diff)


# --------------------------------------------------------------------------- #
# Storage formats
# --------------------------------------------------------------------------- #
def test_passwords_use_argon2id() -> None:
    digest = hash_password("a-very-strong-password")
    assert digest.startswith("$argon2id$")


def test_api_keys_are_stored_hashed() -> None:
    full_key, prefix, hashed = generate_api_key()
    assert hashed == hash_api_key(full_key)
    assert full_key not in hashed
    assert len(hashed) == 64
    assert full_key.startswith(prefix)


async def test_refresh_tokens_are_hashed_at_rest(client, session_factory) -> None:
    await create_user(session_factory)
    await login(client)

    cookie = client.cookies.get("xerex_refresh_token")
    assert cookie

    async with session_factory() as session:
        stored = (await session.execute(select(RefreshToken).limit(1))).scalar_one()

    assert stored.token_hash != cookie
    assert cookie not in stored.token_hash
    assert len(stored.token_hash) == 64


async def test_failed_login_does_not_echo_the_password(client, session_factory) -> None:
    await create_user(session_factory)
    secret_password = "the-wrong-password-9999"

    response = await client.post(
        "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": secret_password}
    )
    assert response.status_code == 401
    assert secret_password not in response.text
    assert response.json()["error"]["code"] == "invalid_credentials"


# --------------------------------------------------------------------------- #
# RBAC: no self-escalation
# --------------------------------------------------------------------------- #
async def _admin_headers(client, session_factory) -> tuple[dict[str, str], str]:
    await create_user(session_factory, email="owner@xerex.ai")
    admin = await create_user(
        session_factory,
        email="admin@xerex.ai",
        password="admin-password-123",
        role=AdminRole.ADMIN,
    )
    token = await login(client, "admin@xerex.ai", "admin-password-123")
    return {"Authorization": f"Bearer {token}"}, str(admin.id)


async def test_admin_cannot_create_an_owner_account(client, session_factory) -> None:
    headers, _ = await _admin_headers(client, session_factory)
    response = await client.post(
        "/api/v1/admin-users",
        headers=headers,
        json={"email": "new.owner@xerex.ai", "password": "another-strong-pass", "role": "owner"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_escalation_not_allowed"


async def test_admin_cannot_promote_another_account_to_owner(client, session_factory) -> None:
    headers, _ = await _admin_headers(client, session_factory)
    created = await client.post(
        "/api/v1/admin-users",
        headers=headers,
        json={"email": "operator@xerex.ai", "password": "operator-pass-123", "role": "operator"},
    )
    assert created.status_code == 201
    operator_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/admin-users/{operator_id}", headers=headers, json={"role": "owner"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "role_escalation_not_allowed"


async def test_administrator_cannot_change_their_own_role(client, session_factory) -> None:
    headers, admin_id = await _admin_headers(client, session_factory)
    response = await client.patch(
        f"/api/v1/admin-users/{admin_id}", headers=headers, json={"role": "owner"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "cannot_change_own_role"


async def test_owner_may_still_promote_an_administrator(client, session_factory) -> None:
    await create_user(session_factory)  # owner@xerex.ai
    admin = await create_user(
        session_factory,
        email="to-promote@xerex.ai",
        password="promote-me-12345",
        role=AdminRole.ADMIN,
    )
    owner_token = await login(client)
    headers = {"Authorization": f"Bearer {owner_token}"}

    response = await client.patch(
        f"/api/v1/admin-users/{admin.id}", headers=headers, json={"role": "operator"}
    )
    assert response.status_code == 200
    assert response.json()["role"] == "operator"
