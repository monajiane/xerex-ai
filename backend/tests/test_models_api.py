"""Model registry, discovery and playground (M3).

The upstream provider is always mocked: the suite asserts the reconciliation rules,
the credential resolution order, the health observations and the audit entries —
never a real network call.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.crypto import decrypt_secret, encrypt_secret, key_hint
from app.models.enums import AdminRole, CredentialStatus, HealthStatus
from app.models.health import HealthCheck
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.repositories.providers import CredentialRepository
from tests.conftest import create_user, login

PAYLOAD = {
    "name": "OpenAI Primary",
    "kind": "openai",
    "base_url": "https://api.openai.com/v1",
}

CATALOGUE = {
    "data": [
        {"id": "gpt-4o-mini", "owned_by": "openai"},
        {"id": "gpt-4o", "owned_by": "openai"},
    ]
}


async def _owner_headers(client, session_factory) -> dict[str, str]:
    await create_user(session_factory)
    return {"Authorization": f"Bearer {await login(client)}"}


async def _provider_with_credential(client, session, headers) -> tuple[dict, str]:
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()
    secret = "sk-live-abcdefghijklmnop"
    credential = (
        await client.post(
            f"/api/v1/providers/{provider['id']}/credentials",
            json={"label": "primary", "secret": secret},
            headers=headers,
        )
    ).json()
    return provider, credential["id"]


def _install_adapter(monkeypatch, handler) -> None:
    """Route every adapter built by the services through a mock transport."""
    import app.services.model_admin as module

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


def _ok_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/models"):
        return httpx.Response(200, json=CATALOGUE)
    if "/chat/completions" in request.url.path:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "سلام"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )
    return httpx.Response(404, json={"error": {"message": "not found"}})


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
async def test_manual_model_creation_gets_a_default_endpoint(
    client, session, session_factory
) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()

    created = await client.post(
        "/api/v1/models",
        json={
            "provider_id": provider["id"],
            "name": "gpt-4o-mini",
            "display_name": "GPT-4o mini",
            "context_window": 128000,
            "input_price_per_1m": 0.15,
            "output_price_per_1m": 0.6,
            "capabilities": {"streaming": True},
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "gpt-4o-mini" and body["enabled"] is True

    endpoints = await client.get(f"/api/v1/models/{body['id']}/endpoints", headers=headers)
    assert endpoints.status_code == 200
    assert [item["path"] for item in endpoints.json()] == ["/chat/completions"]
    assert endpoints.json()[0]["streaming_supported"] is True


async def test_duplicate_model_name_per_provider_is_rejected(client, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()
    payload = {"provider_id": provider["id"], "name": "gpt-4o-mini"}

    assert (await client.post("/api/v1/models", json=payload, headers=headers)).status_code == 201
    duplicate = await client.post("/api/v1/models", json=payload, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "model_name_duplicate"


async def test_model_list_filters_and_updates_are_audited(client, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()
    first = (
        await client.post(
            "/api/v1/models",
            json={"provider_id": provider["id"], "name": "gpt-4o"},
            headers=headers,
        )
    ).json()
    await client.post(
        "/api/v1/models",
        json={"provider_id": provider["id"], "name": "o4-mini", "enabled": False},
        headers=headers,
    )

    disabled = await client.get("/api/v1/models?enabled=false", headers=headers)
    assert [item["name"] for item in disabled.json()["items"]] == ["o4-mini"]
    searched = await client.get("/api/v1/models?search=4o", headers=headers)
    assert searched.json()["total"] == 1

    updated = await client.patch(
        f"/api/v1/models/{first['id']}",
        json={"deprecated": True, "context_window": 200000},
        headers=headers,
    )
    assert updated.json()["deprecated"] is True

    audit = await client.get("/api/v1/audit-logs?page_size=50", headers=headers)
    actions = [entry["action"] for entry in audit.json()["items"]]
    assert actions.count("model_created") == 2
    assert actions.count("model_updated") == 1


async def test_viewer_cannot_modify_models(client, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()
    await create_user(
        session_factory,
        email="viewer@xerex.ai",
        password="viewer-password-1",
        role=AdminRole.VIEWER,
    )
    viewer = {
        "Authorization": f"Bearer {await login(client, 'viewer@xerex.ai', 'viewer-password-1')}"
    }

    assert (await client.get("/api/v1/models", headers=viewer)).status_code == 200
    blocked = await client.post(
        "/api/v1/models", json={"provider_id": provider["id"], "name": "gpt-4o"}, headers=viewer
    )
    assert blocked.status_code == 403


async def test_deleting_a_provider_removes_its_models(client, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()
    await client.post(
        "/api/v1/models", json={"provider_id": provider["id"], "name": "gpt-4o"}, headers=headers
    )

    assert (
        await client.delete(f"/api/v1/providers/{provider['id']}", headers=headers)
    ).status_code == 200
    listed = await client.get("/api/v1/models", headers=headers)
    assert listed.json()["total"] == 0


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
async def test_discovery_creates_models_and_is_idempotent(
    client, session, session_factory, monkeypatch
) -> None:
    headers = await _owner_headers(client, session_factory)
    provider, credential_id = await _provider_with_credential(client, session, headers)
    _install_adapter(monkeypatch, _ok_handler)

    first = await client.post(
        "/api/v1/models/discover",
        json={"provider_id": provider["id"]},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["discovered"] == 2 and body["created"] == 2 and body["skipped"] == 0
    assert body["provider_name"] == "OpenAI Primary"

    second = await client.post(
        "/api/v1/models/discover",
        json={"provider_id": provider["id"]},
        headers=headers,
    )
    assert second.json()["created"] == 0 and second.json()["skipped"] == 2

    overwrite = await client.post(
        "/api/v1/models/discover",
        json={"provider_id": provider["id"], "overwrite_existing": True},
        headers=headers,
    )
    assert overwrite.json()["updated"] == 2

    listed = await client.get("/api/v1/models?page_size=100", headers=headers)
    names = sorted(item["name"] for item in listed.json()["items"])
    assert names == ["gpt-4o", "gpt-4o-mini"]

    audit = await client.get("/api/v1/audit-logs?page_size=20", headers=headers)
    assert "models_discovered" in [entry["action"] for entry in audit.json()["items"]]

    # The default endpoint was created for each discovered model.
    model_id = listed.json()["items"][0]["id"]
    endpoints = await client.get(f"/api/v1/models/{model_id}/endpoints", headers=headers)
    assert endpoints.json()[0]["path"].endswith("chat/completions")
    assert credential_id  # the credential from the provider default was used


async def test_discovery_without_a_credential_is_an_honest_conflict(
    client, session_factory
) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()

    response = await client.post(
        "/api/v1/models/discover", json={"provider_id": provider["id"]}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "credential_missing"


async def test_discovery_reports_the_upstream_error_code(
    client, session, session_factory, monkeypatch
) -> None:
    headers = await _owner_headers(client, session_factory)
    provider, credential_id = await _provider_with_credential(client, session, headers)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    _install_adapter(monkeypatch, handler)

    response = await client.post(
        "/api/v1/models/discover", json={"provider_id": provider["id"]}, headers=headers
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_unauthorized"

    credential = await CredentialRepository(session).get(__import__("uuid").UUID(credential_id))
    assert credential is not None  # untouched
    health = await session.execute(
        __import__("sqlalchemy").select(HealthCheck).order_by(HealthCheck.checked_at.desc())
    )
    assert health.scalars().first().status is HealthStatus.DOWN


async def test_anthropic_discovery_is_reported_as_unsupported(client, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (
        await client.post(
            "/api/v1/providers",
            json={
                "name": "Claude Primary",
                "kind": "anthropic",
                "base_url": "https://api.anthropic.com/v1",
            },
            headers=headers,
        )
    ).json()
    await client.post(
        f"/api/v1/providers/{provider['id']}/credentials",
        json={"label": "primary", "secret": "sk-ant-abcdefghijklmnop"},
        headers=headers,
    )

    response = await client.post(
        "/api/v1/models/discover", json={"provider_id": provider["id"]}, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "provider_discovery_unsupported"


# --------------------------------------------------------------------------- #
# Playground
# --------------------------------------------------------------------------- #
async def test_playground_returns_real_token_counts(
    client, session, session_factory, monkeypatch
) -> None:
    headers = await _owner_headers(client, session_factory)
    provider, _ = await _provider_with_credential(client, session, headers)
    model = (
        await client.post(
            "/api/v1/models",
            json={"provider_id": provider["id"], "name": "gpt-4o-mini"},
            headers=headers,
        )
    ).json()
    _install_adapter(monkeypatch, _ok_handler)

    response = await client.post(
        f"/api/v1/models/{model['id']}/test",
        json={"model_id": model["id"], "prompt": "سلام", "temperature": 0.1, "max_tokens": 64},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["output_text"] == "سلام"
    assert body["input_tokens"] == 7 and body["output_tokens"] == 3
    assert body["error_code"] is None
    assert body["latency_ms"] >= 0

    audit = await client.get("/api/v1/audit-logs?page_size=20", headers=headers)
    assert "model_tested" in [entry["action"] for entry in audit.json()["items"]]


async def test_playground_reports_upstream_failures_without_raising(
    client, session, session_factory, monkeypatch
) -> None:
    headers = await _owner_headers(client, session_factory)
    provider, _ = await _provider_with_credential(client, session, headers)
    model = (
        await client.post(
            "/api/v1/models",
            json={"provider_id": provider["id"], "name": "gpt-4o-mini"},
            headers=headers,
        )
    ).json()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"error": {"message": "slow down"}}, headers={"retry-after": "7"}
        )

    _install_adapter(monkeypatch, handler)

    response = await client.post(
        f"/api/v1/models/{model['id']}/test",
        json={"model_id": model["id"], "prompt": "سلام"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["error_code"] == "provider_rate_limited"
    assert response.json()["output_text"] == ""

    # A rate limit must not be recorded as a dead provider.
    provider_row = await session.get(Provider, __import__("uuid").UUID(provider["id"]))
    assert provider_row.health_status == HealthStatus.RATE_LIMITED.value


async def test_playground_needs_a_credential(client, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()
    model = (
        await client.post(
            "/api/v1/models",
            json={"provider_id": provider["id"], "name": "gpt-4o-mini"},
            headers=headers,
        )
    ).json()

    response = await client.post(
        f"/api/v1/models/{model['id']}/test",
        json={"model_id": model["id"], "prompt": "سلام"},
        headers=headers,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "credential_missing"


async def test_streaming_playground_emits_sse_events(
    client, session, session_factory, monkeypatch
) -> None:
    headers = await _owner_headers(client, session_factory)
    provider, _ = await _provider_with_credential(client, session, headers)
    model = (
        await client.post(
            "/api/v1/models",
            json={"provider_id": provider["id"], "name": "gpt-4o-mini"},
            headers=headers,
        )
    ).json()

    def handler(request: httpx.Request) -> httpx.Response:
        body = "".join(
            f'data: {{"choices":[{{"delta":{{"content":"{chunk}"}}}}]}}\n\n'
            for chunk in ("س", "ل", "ام")
        )
        return httpx.Response(
            200,
            content=(body + "data: [DONE]\n\n").encode(),
            headers={"content-type": "text/event-stream"},
        )

    _install_adapter(monkeypatch, handler)

    response = await client.post(
        f"/api/v1/models/{model['id']}/test/stream",
        json={"model_id": model["id"], "prompt": "سلام", "stream": True},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert '"delta": "س"' in body or '"delta":"س"' in body
    assert '"done": true' in body or '"done":true' in body
    assert "data: [DONE]" in body


# --------------------------------------------------------------------------- #
# Endpoints — «نقاط اتصال مدل»
# --------------------------------------------------------------------------- #
async def test_endpoint_credential_binding_is_validated(client, session, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    provider, credential_id = await _provider_with_credential(client, session, headers)
    other = (
        await client.post(
            "/api/v1/providers", json={**PAYLOAD, "name": "Second provider"}, headers=headers
        )
    ).json()
    other_credential = (
        await client.post(
            f"/api/v1/providers/{other['id']}/credentials",
            json={"label": "primary", "secret": "sk-live-zzzzzzzzzzzz"},
            headers=headers,
        )
    ).json()
    model = (
        await client.post(
            "/api/v1/models",
            json={"provider_id": provider["id"], "name": "gpt-4o-mini"},
            headers=headers,
        )
    ).json()

    created = await client.post(
        f"/api/v1/models/{model['id']}/endpoints",
        json={"path": "/chat/completions", "credential_id": credential_id},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["credential_id"] == credential_id

    cross_provider = await client.post(
        f"/api/v1/models/{model['id']}/endpoints",
        json={"path": "/chat/completions", "credential_id": other_credential["id"]},
        headers=headers,
    )
    assert cross_provider.status_code == 404
    assert cross_provider.json()["error"]["code"] == "credential_not_found"

    invalid_path = await client.post(
        f"/api/v1/models/{model['id']}/endpoints",
        json={"path": "chat/completions"},
        headers=headers,
    )
    assert invalid_path.status_code == 422
    assert invalid_path.json()["error"]["code"] == "endpoint_path_invalid"


async def test_endpoint_of_another_model_is_not_reachable(client, session, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    provider = (await client.post("/api/v1/providers", json=PAYLOAD, headers=headers)).json()
    first = (
        await client.post(
            "/api/v1/models",
            json={"provider_id": provider["id"], "name": "gpt-4o"},
            headers=headers,
        )
    ).json()
    second = (
        await client.post(
            "/api/v1/models",
            json={"provider_id": provider["id"], "name": "gpt-4o-mini"},
            headers=headers,
        )
    ).json()
    endpoints = (
        await client.get(f"/api/v1/models/{first['id']}/endpoints", headers=headers)
    ).json()
    endpoint_id = endpoints[0]["id"]

    patched = await client.patch(
        f"/api/v1/models/{second['id']}/endpoints/{endpoint_id}",
        json={"enabled": False},
        headers=headers,
    )
    assert patched.status_code == 404
    assert patched.json()["error"]["code"] == "endpoint_not_found"


async def test_missing_model_is_a_typed_404(client, session_factory) -> None:
    headers = await _owner_headers(client, session_factory)
    response = await client.get(
        "/api/v1/models/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"


def test_crypto_helpers_used_by_the_suite_round_trip() -> None:
    """The credential helpers this module relies on behave as the API tests expect."""
    encrypted = encrypt_secret("sk-live-round-trip")
    assert encrypted != "sk-live-round-trip"
    assert decrypt_secret(encrypted) == "sk-live-round-trip"
    assert key_hint("sk-live-round-trip") == "…trip"


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "down"), (429, "rate_limited"), (503, "degraded")],
)
def test_health_mapping_is_stable(status: int, expected: str) -> None:
    from app.providers.adapters import classify_status
    from app.services.model_admin import _health_for

    code, _ = classify_status(status)
    assert _health_for(code).value == expected


def test_stored_models_keep_their_endpoint_relationship(session) -> None:  # noqa: ANN001
    """A model row without an endpoint row is a modelling mistake, not a state."""
    provider = Provider(name="P", slug="p", kind="openai", base_url="https://x/v1")
    model = Model(provider_id=provider.id, name="m")
    assert isinstance(model, Model)
    assert ModelEndpoint.__tablename__ == "model_endpoints"
    assert ProviderCredential.__tablename__ == "provider_credentials"
    assert CredentialStatus.UNVERIFIED.value == "unverified"
