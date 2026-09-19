"""Provider and credential administration: CRUD, RBAC, secrets and audit (M2)."""

from __future__ import annotations

import uuid

import httpx

from app.core.crypto import decrypt_secret
from app.models.enums import AdminRole, CredentialStatus
from app.models.providers import ProviderCredential
from app.repositories.providers import CredentialRepository, ProviderRepository
from tests.conftest import create_user, login

PAYLOAD = {
    "name": "OpenAI Primary",
    "kind": "openai",
    "base_url": "https://api.openai.com/v1",
    "description": "Main OpenAI account",
    "priority": 10,
    "weight": 100,
    "timeout_ms": 20000,
    "max_retries": 2,
}


async def _viewer_headers(client, session_factory) -> dict[str, str]:
    await create_user(
        session_factory,
        email="viewer@xerex.ai",
        password="viewer-password-1",
        role=AdminRole.VIEWER,
    )
    token = await login(client, "viewer@xerex.ai", "viewer-password-1")
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
async def test_create_provider_generates_slug_and_returns_counts(client, session_factory) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}

    response = await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["slug"] == "openai-primary"
    assert body["credential_count"] == 0 and body["model_count"] == 0
    assert body["kind"] == "openai" and body["enabled"] is True
    assert "secret" not in response.text.lower()


async def test_slug_collisions_get_a_suffix(client, session_factory) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}

    first = await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)
    second = await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)
    assert first.json()["slug"] == "openai-primary"
    assert second.json()["slug"] == "openai-primary-2"


async def test_list_filters_and_pagination(client, session_factory) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)
    await client.post(
        "/api/v1/providers",
        json={
            **PAYLOAD,
            "name": "DeepSeek",
            "kind": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "enabled": False,
        },
        headers=headers,
    )

    everything = await client.get("/api/v1/providers", headers=headers)
    assert everything.json()["total"] == 2

    disabled = await client.get("/api/v1/providers?enabled=false", headers=headers)
    assert [item["name"] for item in disabled.json()["items"]] == ["DeepSeek"]

    by_kind = await client.get("/api/v1/providers?kind=openai", headers=headers)
    assert [item["name"] for item in by_kind.json()["items"]] == ["OpenAI Primary"]

    searched = await client.get("/api/v1/providers?search=deep", headers=headers)
    assert searched.json()["total"] == 1

    paged = await client.get("/api/v1/providers?page=2&page_size=1", headers=headers)
    assert paged.json()["page"] == 2 and len(paged.json()["items"]) == 1


async def test_update_records_only_real_changes(client, session_factory) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    created = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()

    same = await client.patch(
        f"/api/v1/providers/{created['id']}", json={"name": PAYLOAD["name"]}, headers=headers
    )
    assert same.status_code == 200

    changed = await client.patch(
        f"/api/v1/providers/{created['id']}",
        json={"priority": 5, "enabled": False},
        headers=headers,
    )
    assert changed.json()["priority"] == 5
    assert changed.json()["enabled"] is False

    audit = await client.get("/api/v1/audit-logs?page_size=50", headers=headers)
    actions = [entry["action"] for entry in audit.json()["items"]]
    assert actions.count("provider_created") == 1
    assert actions.count("provider_updated") == 1  # the no-op PATCH wrote nothing


async def test_missing_provider_returns_english_envelope(client, session_factory) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    missing = uuid.uuid4()

    response = await client.get(f"/api/v1/providers/{missing}", headers=headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "provider_not_found"
    assert response.json()["error"]["request_id"]


async def test_delete_removes_credentials_and_models_by_cascade(
    client, session, session_factory
) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    created = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()
    await client.post(
        f"/api/v1/providers/{created['id']}/credentials",
        json={"label": "primary", "secret": "sk-live-abcdefghijklmnop"},
        headers=headers,
    )

    deleted = await client.delete(f"/api/v1/providers/{created['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"

    remaining = await CredentialRepository(session).count_for_provider(uuid.UUID(created["id"]))
    assert remaining == 0
    audit = await client.get("/api/v1/audit-logs?page_size=50", headers=headers)
    assert "provider_deleted" in [entry["action"] for entry in audit.json()["items"]]


# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #
async def test_viewer_can_read_but_not_write(client, session_factory) -> None:
    await create_user(session_factory)
    owner_headers = {"Authorization": f"Bearer {await login(client)}"}
    await client.post("/api/v1/providers", json=PAYLOAD, headers=owner_headers)
    viewer_headers = await _viewer_headers(client, session_factory)

    assert (await client.get("/api/v1/providers", headers=viewer_headers)).status_code == 200
    blocked = await client.post("/api/v1/providers", json=PAYLOAD, headers=viewer_headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "insufficient_role"


async def test_operator_may_test_but_not_configure(client, session_factory) -> None:
    await create_user(session_factory)
    owner_headers = {"Authorization": f"Bearer {await login(client)}"}
    created = (await client.post("/api/v1/providers", json=PAYLOAD, headers=owner_headers)).json()

    await create_user(
        session_factory,
        email="operator@xerex.ai",
        password="operator-password-1",
        role=AdminRole.OPERATOR,
    )
    token = await login(client, "operator@xerex.ai", "operator-password-1")
    operator_headers = {"Authorization": f"Bearer {token}"}

    # No credential is configured yet, so the honest answer is a failure, not a crash.
    tested = await client.post(f"/api/v1/providers/{created['id']}/test", headers=operator_headers)
    assert tested.status_code == 200
    assert tested.json()["ok"] is False
    assert tested.json()["error_code"] == "credential_missing"

    blocked = await client.patch(
        f"/api/v1/providers/{created['id']}", json={"enabled": False}, headers=operator_headers
    )
    assert blocked.status_code == 403


async def test_anonymous_access_is_rejected(client) -> None:
    assert (await client.get("/api/v1/providers")).status_code == 401


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #
async def _make_provider(client, headers) -> dict:
    return (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()


async def test_credential_secret_is_encrypted_and_never_returned(
    client, session, session_factory
) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    provider = await _make_provider(client, headers)
    secret = "sk-live-0123456789abcdefghijkl"

    created = await client.post(
        f"/api/v1/providers/{provider['id']}/credentials",
        json={"label": "primary", "secret": secret},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert secret not in created.text
    assert body["key_hint"] == "…cdefghijkl"[-8:] or body["key_hint"].endswith("ijkl")
    assert body["status"] == CredentialStatus.UNVERIFIED.value

    stored = await CredentialRepository(session).get(uuid.UUID(body["id"]))
    assert stored is not None
    assert stored.encrypted_secret != secret
    assert decrypt_secret(stored.encrypted_secret) == secret

    listed = await client.get(f"/api/v1/providers/{provider['id']}/credentials", headers=headers)
    assert secret not in listed.text


async def test_duplicate_credential_label_is_rejected(client, session_factory) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    provider = await _make_provider(client, headers)
    payload = {"label": "primary", "secret": "sk-live-abcdefghijklmnop"}
    first = await client.post(
        f"/api/v1/providers/{provider['id']}/credentials", json=payload, headers=headers
    )
    second = await client.post(
        f"/api/v1/providers/{provider['id']}/credentials", json=payload, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "credential_label_duplicate"


async def test_rotate_replaces_the_ciphertext(client, session, session_factory) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    provider = await _make_provider(client, headers)
    created = (
        await client.post(
            f"/api/v1/providers/{provider['id']}/credentials",
            json={"label": "primary", "secret": "sk-live-oldoldoldoldold"},
            headers=headers,
        )
    ).json()

    rotated = await client.post(
        f"/api/v1/providers/{provider['id']}/credentials/{created['id']}/rotate",
        json={"secret": "sk-live-newnewnewnewnew"},
        headers=headers,
    )
    assert rotated.status_code == 200
    assert rotated.json()["status"] == CredentialStatus.UNVERIFIED.value

    stored = await CredentialRepository(session).get(uuid.UUID(created["id"]))
    assert decrypt_secret(stored.encrypted_secret) == "sk-live-newnewnewnewnew"


async def test_verify_credential_records_health_and_status(
    client, session, session_factory, monkeypatch
) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    provider = await _make_provider(client, headers)
    created = (
        await client.post(
            f"/api/v1/providers/{provider['id']}/credentials",
            json={"label": "primary", "secret": "sk-live-abcdefghijklmnop"},
            headers=headers,
        )
    ).json()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "gpt-4o-mini"}]})

    import app.services.provider_admin as admin_module

    real_build = admin_module.build_adapter

    def fake_build(*, kind, base_url, secret, timeout_ms=30_000, client=None):  # noqa: ANN001
        return real_build(
            kind=kind,
            base_url=base_url,
            secret=secret,
            timeout_ms=timeout_ms,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(admin_module, "build_adapter", fake_build)

    verified = await client.post(
        f"/api/v1/providers/{provider['id']}/credentials/{created['id']}/verify",
        headers=headers,
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["ok"] is True
    assert verified.json()["model_count"] == 1

    stored = await CredentialRepository(session).get(uuid.UUID(created["id"]))
    assert stored.status == CredentialStatus.ACTIVE
    assert stored.last_verified_at is not None
    assert stored.last_error_code is None

    provider_row = await ProviderRepository(session).get(uuid.UUID(provider["id"]))
    assert provider_row.health_status == "healthy"


async def test_failed_verification_marks_the_credential_invalid(
    client, session, session_factory, monkeypatch
) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    provider = await _make_provider(client, headers)
    created = (
        await client.post(
            f"/api/v1/providers/{provider['id']}/credentials",
            json={"label": "primary", "secret": "sk-live-wrongkeywrongkey"},
            headers=headers,
        )
    ).json()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "invalid_api_key"}})

    import app.services.provider_admin as admin_module

    real_build = admin_module.build_adapter

    def fake_build(*, kind, base_url, secret, timeout_ms=30_000, client=None):  # noqa: ANN001
        return real_build(
            kind=kind,
            base_url=base_url,
            secret=secret,
            timeout_ms=timeout_ms,
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )

    monkeypatch.setattr(admin_module, "build_adapter", fake_build)

    verified = await client.post(
        f"/api/v1/providers/{provider['id']}/credentials/{created['id']}/verify",
        headers=headers,
    )
    assert verified.json()["ok"] is False
    assert verified.json()["error_code"] == "provider_unauthorized"

    stored = await CredentialRepository(session).get(uuid.UUID(created["id"]))
    assert stored.status == CredentialStatus.INVALID
    assert stored.last_error_code == "provider_unauthorized"


async def test_deleting_a_credential_unbinds_endpoints(client, session, session_factory) -> None:
    from app.models.providers import Model, ModelEndpoint

    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    provider = await _make_provider(client, headers)
    credential = (
        await client.post(
            f"/api/v1/providers/{provider['id']}/credentials",
            json={"label": "primary", "secret": "sk-live-abcdefghijklmnop"},
            headers=headers,
        )
    ).json()

    model = Model(provider_id=uuid.UUID(provider["id"]), name="gpt-4o-mini")
    session.add(model)
    await session.flush()
    endpoint = ModelEndpoint(
        model_id=model.id, credential_id=uuid.UUID(credential["id"]), path="/chat/completions"
    )
    session.add(endpoint)
    await session.commit()

    deleted = await client.delete(
        f"/api/v1/providers/{provider['id']}/credentials/{credential['id']}", headers=headers
    )
    assert deleted.status_code == 200

    await session.refresh(endpoint)
    assert endpoint.credential_id is None  # falls back to the provider default
    assert await session.get(ProviderCredential, uuid.UUID(credential["id"])) is None


async def test_credential_of_another_provider_is_not_reachable(client, session_factory) -> None:
    """Every credential route is scoped by provider, so a mismatched pair is a 404."""
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    first = await _make_provider(client, headers)
    second = (
        await client.post("/api/v1/providers", json={**PAYLOAD, "name": "Second"}, headers=headers)
    ).json()
    credential = (
        await client.post(
            f"/api/v1/providers/{first['id']}/credentials",
            json={"label": "primary", "secret": "sk-live-abcdefghijklmnop"},
            headers=headers,
        )
    ).json()

    patched = await client.patch(
        f"/api/v1/providers/{second['id']}/credentials/{credential['id']}",
        json={"label": "renamed"},
        headers=headers,
    )
    assert patched.status_code == 404
    assert patched.json()["error"]["code"] == "credential_not_found"

    verified = await client.post(
        f"/api/v1/providers/{second['id']}/credentials/{credential['id']}/verify",
        headers=headers,
    )
    assert verified.status_code == 404


async def test_default_credential_endpoint_returns_the_first_credential(
    client, session_factory
) -> None:
    await create_user(session_factory)
    headers = {"Authorization": f"Bearer {await login(client)}"}
    provider = await _make_provider(client, headers)

    empty = await client.get(
        f"/api/v1/providers/{provider['id']}/default-credential", headers=headers
    )
    assert empty.status_code == 200 and empty.json() is None

    created = (
        await client.post(
            f"/api/v1/providers/{provider['id']}/credentials",
            json={"label": "primary", "secret": "sk-live-abcdefghijklmnop"},
            headers=headers,
        )
    ).json()
    resolved = await client.get(
        f"/api/v1/providers/{provider['id']}/default-credential", headers=headers
    )
    assert resolved.json()["id"] == created["id"]
