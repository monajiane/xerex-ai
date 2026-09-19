"""Gateway and API-key administration (M4).

Every upstream call is mocked; the suite asserts what the gateway promises instead:
authentication and scopes, rate limits, quotas, explicit candidate resolution,
per-attempt usage accounting, failover ordering and OpenAI-compatible errors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.models.enums import AdminRole, ClientRequestState, CredentialStatus, HealthStatus
from app.models.health import HealthCheck
from app.models.usage import ApiKey, ClientRequest, UsageRecord
from tests.conftest import create_user, login

PROVIDER = {
    "name": "OpenAI Primary",
    "kind": "openai",
    "base_url": "https://api.openai.com/v1",
    "priority": 1,
}

CHAT_ANSWER = "سلام! چطور می‌توانم کمک کنم؟"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
async def _headers(client, session_factory) -> dict[str, str]:
    await create_user(session_factory)
    return {"Authorization": f"Bearer {await login(client)}"}


async def _provider_with_credential(
    client, headers: dict[str, str], *, name: str = "OpenAI Primary", priority: int = 1
) -> dict:
    payload = {**PROVIDER, "name": name, "priority": priority}
    provider = (await client.post("/api/v1/providers", json=payload, headers=headers)).json()
    credential = (
        await client.post(
            f"/api/v1/providers/{provider['id']}/credentials",
            json={"label": "primary", "secret": "sk-live-abcdefghijklmnop"},
            headers=headers,
        )
    ).json()
    assert credential["status"] == CredentialStatus.UNVERIFIED.value, credential
    return provider


async def _register_model(
    client,
    headers: dict[str, str],
    provider: dict,
    *,
    name: str = "gpt-4o-mini",
    prices: bool = True,
) -> dict:
    body = {
        "provider_id": provider["id"],
        "name": name,
        **({"input_price_per_1m": 3.0, "output_price_per_1m": 15.0} if prices else {}),
    }
    response = await client.post("/api/v1/models", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _issue_key(client, headers: dict[str, str], **overrides: object) -> tuple[str, dict]:
    payload: dict[str, object] = {
        "name": "Test key",
        "scopes": ["chat", "embeddings", "models"],
        "rate_limit_per_min": 60,
    }
    payload.update(overrides)
    response = await client.post("/api/v1/api-keys", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    return body["secret"], body


def _install_adapter(monkeypatch, handler) -> None:  # noqa: ANN001
    import app.services.gateway as module

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


def _chat_handler(request: httpx.Request) -> httpx.Response:
    if "/chat/completions" in request.url.path:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": CHAT_ANSWER}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
        )
    if request.url.path.endswith("/embeddings"):
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})
    return httpx.Response(404, json={"error": {"message": "not found"}})


CHAT_REQUEST = {
    "model": "gpt-4o-mini",
    "messages": [{"role": "user", "content": "سلام"}],
}


def _usage(**kwargs: object) -> UsageRecord:
    """One attempt row with the mandatory timestamp filled in."""
    return UsageRecord(created_at=datetime.now(UTC), **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Authentication, scopes, limits
# --------------------------------------------------------------------------- #
async def test_gateway_requires_an_api_key(client, session_factory) -> None:
    response = await client.post("/v1/chat/completions", json=CHAT_REQUEST)
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "invalid_api_key"
    assert body["error"]["type"] == "authentication_error"
    assert "message" in body["error"]


async def test_gateway_rejects_unknown_and_revoked_keys(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    unknown = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": "Bearer xrx_live_nope"}
    )
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "invalid_api_key"

    secret, record = await _issue_key(client, headers)
    revoke = await client.post(f"/api/v1/api-keys/{record['id']}/revoke", headers=headers)
    assert revoke.status_code == 200
    revoked = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert revoked.status_code == 401
    assert revoked.json()["error"]["code"] == "invalid_api_key"


async def test_x_api_key_header_is_accepted(client, session_factory, monkeypatch) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    await _register_model(client, headers, provider)
    secret, _ = await _issue_key(client, headers)
    _install_adapter(monkeypatch, _chat_handler)

    response = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"x-api-key": secret}
    )
    assert response.status_code == 200, response.text


async def test_scope_is_enforced_per_endpoint(client, session_factory, monkeypatch) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    await _register_model(client, headers, provider)
    secret, _ = await _issue_key(client, headers, scopes=["chat"])
    _install_adapter(monkeypatch, _chat_handler)

    chat_ok = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert chat_ok.status_code == 200, "the chat scope is enough for chat completions"

    embeddings = await client.post(
        "/v1/embeddings",
        json={"model": "gpt-4o-mini", "input": "سلام"},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert embeddings.status_code == 403
    assert embeddings.json()["error"]["code"] == "insufficient_scope"

    catalogue = await client.get("/v1/models", headers={"Authorization": f"Bearer {secret}"})
    assert catalogue.status_code == 403
    assert catalogue.json()["error"]["code"] == "insufficient_scope"


async def test_rate_limited_key_answers_429_with_retry_after(
    client, session_factory, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    secret, _ = await _issue_key(client, headers)

    import app.api.gateway.deps as deps_module
    from app.services.rate_limit import RateLimitResult

    async def deny(*_args: object, **_kwargs: object) -> RateLimitResult:
        return RateLimitResult(
            allowed=False, remaining=0, retry_after_seconds=42, limit=60, backend="redis"
        )

    monkeypatch.setattr(deps_module.gateway_limiter, "hit", deny)
    response = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limit_exceeded"
    assert response.headers["Retry-After"] == "42"


async def test_quota_exhausted_key_is_rejected(client, session_factory, session) -> None:
    headers = await _headers(client, session_factory)
    secret, record = await _issue_key(client, headers, quota_tokens=100)

    stored = await session.get(ApiKey, uuid.UUID(record["id"]))
    assert stored is not None
    session.add(
        _usage(
            request_id="req-quota",
            api_key_id=stored.id,
            input_tokens=60,
            output_tokens=60,
            total_tokens=120,
        )
    )
    await session.commit()

    response = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "quota_exceeded"


async def test_gateway_can_be_disabled(client, session_factory, monkeypatch) -> None:
    from app.core.config import settings

    headers = await _headers(client, session_factory)
    secret, _ = await _issue_key(client, headers)
    monkeypatch.setattr(settings, "gateway_enabled", False)
    response = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "gateway_disabled"


async def test_public_validation_errors_use_the_openai_shape(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    secret, _ = await _issue_key(client, headers)
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o-mini", "messages": []},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["request_id"]


# --------------------------------------------------------------------------- #
# Chat completions
# --------------------------------------------------------------------------- #
async def test_chat_completion_is_recorded_per_attempt(
    client, session_factory, session, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    model = await _register_model(client, headers, provider)
    secret, record = await _issue_key(client, headers)
    _install_adapter(monkeypatch, _chat_handler)

    response = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == CHAT_ANSWER
    assert body["usage"] == {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
    # The answer says where it came from, which is what makes failover debuggable.
    assert body["xerex"]["provider_id"] == provider["id"]
    assert body["xerex"]["credential_id"]
    assert body["xerex"]["request_id"] == response.headers["x-request-id"]

    client_requests = (
        (
            await session.execute(
                select(ClientRequest).where(ClientRequest.api_key_id == uuid.UUID(record["id"]))
            )
        )
        .scalars()
        .all()
    )
    assert len(client_requests) == 1
    stored = client_requests[0]
    assert stored.state == ClientRequestState.SUCCEEDED
    assert stored.attempt_count == 1
    assert stored.total_tokens == 10
    assert stored.final_status_code == 200

    attempts = (
        (
            await session.execute(
                select(UsageRecord).where(UsageRecord.client_request_id == stored.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.provider_id is not None
    assert attempt.credential_id is not None
    assert attempt.model_id is not None
    assert attempt.endpoint_id is not None
    assert attempt.attempt_number == 1
    assert attempt.is_final is True
    assert attempt.input_tokens == 7
    assert attempt.output_tokens == 3
    # 7 input tokens at 3 USD/1M + 3 output tokens at 15 USD/1M
    assert float(attempt.cost) == pytest.approx(0.000066, abs=1e-9)
    assert float(stored.cost) == pytest.approx(0.000066, abs=1e-9)
    assert attempt.model_id == model["id"] or str(attempt.model_id) == model["id"]


async def test_failover_records_every_attempt(
    client, session_factory, session, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    primary = await _provider_with_credential(client, headers, name="Primary", priority=1)
    secondary = await _provider_with_credential(client, headers, name="Secondary", priority=2)
    await _register_model(client, headers, primary)
    await _register_model(client, headers, secondary)
    secret, record = await _issue_key(client, headers)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "primary.example":
            return httpx.Response(429, json={"error": {"message": "slow down"}})
        return _chat_handler(request)

    # Both providers point at their own host so the mock can fail only the first one.
    await client.patch(
        f"/api/v1/providers/{primary['id']}",
        json={"base_url": "https://primary.example/v1"},
        headers=headers,
    )
    await client.patch(
        f"/api/v1/providers/{secondary['id']}",
        json={"base_url": "https://secondary.example/v1"},
        headers=headers,
    )
    _install_adapter(monkeypatch, handler)

    response = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["xerex"]["provider_id"] == secondary["id"]

    stored = (
        await session.execute(
            select(ClientRequest).where(ClientRequest.api_key_id == uuid.UUID(record["id"]))
        )
    ).scalar_one()
    assert stored.state == ClientRequestState.SUCCEEDED
    assert stored.attempt_count == 2
    attempts = (
        (
            await session.execute(
                select(UsageRecord)
                .where(UsageRecord.client_request_id == stored.id)
                .order_by(UsageRecord.attempt_number)
            )
        )
        .scalars()
        .all()
    )
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert attempts[0].error_code == "provider_rate_limited"
    assert attempts[0].retryable is True
    assert attempts[0].is_final is False
    assert attempts[1].error_code is None
    assert attempts[1].is_final is True


async def test_rate_limited_provider_is_recorded_in_health(
    client, session_factory, session, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    await _register_model(client, headers, provider)
    secret, _ = await _issue_key(client, headers)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "slow down"}})

    _install_adapter(monkeypatch, handler)
    response = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "provider_rate_limited"

    observations = (
        (
            await session.execute(
                select(HealthCheck).where(HealthCheck.provider_id == uuid.UUID(provider["id"]))
            )
        )
        .scalars()
        .all()
    )
    assert observations, "a failed provider call must leave a health observation"
    assert {row.status for row in observations} == {HealthStatus.RATE_LIMITED}


async def test_upstream_client_error_is_not_retried(
    client, session_factory, session, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    primary = await _provider_with_credential(client, headers, name="Primary", priority=1)
    secondary = await _provider_with_credential(client, headers, name="Secondary", priority=2)
    await _register_model(client, headers, primary)
    await _register_model(client, headers, secondary)
    secret, record = await _issue_key(client, headers)

    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host or "")
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    _install_adapter(monkeypatch, handler)
    response = await client.post(
        "/v1/chat/completions", json=CHAT_REQUEST, headers={"Authorization": f"Bearer {secret}"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "provider_bad_request"
    assert len(calls) == 1, "a 400 is not retryable and must not fail over"

    stored = (
        await session.execute(
            select(ClientRequest).where(ClientRequest.api_key_id == uuid.UUID(record["id"]))
        )
    ).scalar_one()
    assert stored.state == ClientRequestState.FAILED
    assert stored.final_error_code == "provider_bad_request"


async def test_unknown_model_answers_404(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    secret, _ = await _issue_key(client, headers)
    response = await client.post(
        "/v1/chat/completions",
        json={"model": "ghost-model", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "model_not_found"
    assert response.json()["error"]["param"] == "model"


async def test_streaming_fails_before_the_stream_starts(
    client, session_factory, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    secret, _ = await _issue_key(client, headers)
    _install_adapter(monkeypatch, _chat_handler)
    response = await client.post(
        "/v1/chat/completions",
        json={**CHAT_REQUEST, "model": "ghost-model", "stream": True},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["error"]["code"] == "model_not_found"


async def test_streaming_emits_openai_chunks(client, session_factory, session, monkeypatch) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    await _register_model(client, headers, provider)
    secret, record = await _issue_key(client, headers)

    def handler(request: httpx.Request) -> httpx.Response:
        body = b"".join(
            [
                b'data: {"choices": [{"delta": {"content": "\xd8\xb3"}}]}\n\n',
                b"data: [DONE]\n\n",
            ]
        )
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    _install_adapter(monkeypatch, handler)
    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json={**CHAT_REQUEST, "stream": True},
        headers={"Authorization": f"Bearer {secret}"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-cache"
        text = "".join([chunk async for chunk in response.aiter_text()])

    assert '"object": "chat.completion.chunk"' in text
    assert '"finish_reason": "stop"' in text
    assert text.rstrip().endswith("data: [DONE]")

    stored = (
        await session.execute(
            select(ClientRequest).where(ClientRequest.api_key_id == uuid.UUID(record["id"]))
        )
    ).scalar_one()
    assert stored.streaming is True
    assert stored.state == ClientRequestState.SUCCEEDED
    attempt = (
        await session.execute(select(UsageRecord).where(UsageRecord.client_request_id == stored.id))
    ).scalar_one()
    assert attempt.streaming is True


async def test_streaming_reports_an_upstream_failure_in_band(
    client, session_factory, session, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    await _register_model(client, headers, provider)
    secret, record = await _issue_key(client, headers)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "boom"}})

    _install_adapter(monkeypatch, handler)
    async with client.stream(
        "POST",
        "/v1/chat/completions",
        json={**CHAT_REQUEST, "stream": True},
        headers={"Authorization": f"Bearer {secret}"},
    ) as response:
        text = "".join([chunk async for chunk in response.aiter_text()])

    # 5xx from the upstream is classified as a retryable provider error
    assert "provider_error" in text
    assert text.rstrip().endswith("data: [DONE]")

    stored = (
        await session.execute(
            select(ClientRequest).where(ClientRequest.api_key_id == uuid.UUID(record["id"]))
        )
    ).scalar_one()
    assert stored.state == ClientRequestState.FAILED
    assert stored.final_error_code == "provider_error"


# --------------------------------------------------------------------------- #
# Completions, embeddings, catalogue
# --------------------------------------------------------------------------- #
async def test_legacy_completions_are_mapped_onto_chat(
    client, session_factory, monkeypatch
) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    await _register_model(client, headers, provider)
    secret, _ = await _issue_key(client, headers)
    _install_adapter(monkeypatch, _chat_handler)

    response = await client.post(
        "/v1/completions",
        json={"model": "gpt-4o-mini", "prompt": "سلام", "max_tokens": 32},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object"] == "text_completion"
    assert body["choices"][0]["text"] == CHAT_ANSWER
    assert body["usage"]["total_tokens"] == 10


async def test_embeddings_are_returned_and_recorded(client, session_factory, monkeypatch) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    await _register_model(client, headers, provider)
    secret, record = await _issue_key(client, headers)
    _install_adapter(monkeypatch, _chat_handler)

    response = await client.post(
        "/v1/embeddings",
        json={"model": "gpt-4o-mini", "input": ["سلام", "دنیا"]},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["object"] == "list"
    assert body["data"][0]["object"] == "embedding"
    assert body["usage"]["total_tokens"] == 0  # embeddings usage is provider-reported

    async with session_factory() as check:
        attempts = (
            (
                await check.execute(
                    select(UsageRecord).where(UsageRecord.api_key_id == uuid.UUID(record["id"]))
                )
            )
            .scalars()
            .all()
        )
    assert len(attempts) == 1
    assert attempts[0].status_code == 200


async def test_models_catalogue_only_lists_enabled_models(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    provider = await _provider_with_credential(client, headers)
    await _register_model(client, headers, provider, name="gpt-4o-mini")
    hidden = await _register_model(client, headers, provider, name="gpt-4o")
    await client.patch(f"/api/v1/models/{hidden['id']}", json={"enabled": False}, headers=headers)
    secret, _ = await _issue_key(client, headers)

    response = await client.get("/v1/models", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert [entry["id"] for entry in body["data"]] == ["gpt-4o-mini"]
    assert body["data"][0]["owned_by"] == provider["slug"]

    one = await client.get("/v1/models/gpt-4o-mini", headers={"Authorization": f"Bearer {secret}"})
    assert one.status_code == 200
    assert one.json()["id"] == "gpt-4o-mini"

    missing = await client.get("/v1/models/nope", headers={"Authorization": f"Bearer {secret}"})
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "model_not_found"


async def test_info_reports_the_calling_key(client, session_factory, session) -> None:
    headers = await _headers(client, session_factory)
    secret, record = await _issue_key(client, headers, quota_tokens=500)
    session.add(_usage(request_id="req-info", api_key_id=uuid.UUID(record["id"]), total_tokens=120))
    await session.commit()

    response = await client.get("/v1/info", headers={"Authorization": f"Bearer {secret}"})
    assert response.status_code == 200
    body = response.json()
    assert body["key"]["prefix"] == record["prefix"]
    assert body["key"]["scopes"] == ["chat", "embeddings", "models"]
    assert body["usage"] == {"total_tokens": 120, "remaining_tokens": 380}
    assert "/v1/chat/completions" in body["endpoints"]


# --------------------------------------------------------------------------- #
# API key administration
# --------------------------------------------------------------------------- #
async def test_created_key_is_returned_once_and_stored_hashed(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    secret, record = await _issue_key(client, headers, name="Production")

    assert secret.startswith("xrx_live_")
    assert record["masked"].startswith(record["prefix"])
    assert (
        "secret"
        not in (await client.get(f"/api/v1/api-keys/{record['id']}", headers=headers)).json()
    )
    assert record["enabled"] is True
    assert record["revoked_at"] is None

    listed = (await client.get("/api/v1/api-keys", headers=headers)).json()
    assert listed["total"] == 1
    assert listed["items"][0]["name"] == "Production"
    assert secret not in str(listed)


async def test_key_update_scopes_and_expiry_are_validated(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    _, record = await _issue_key(client, headers)
    bad_scope = await client.post(
        "/api/v1/api-keys",
        json={"name": "bad", "scopes": ["teleport"]},
        headers=headers,
    )
    assert bad_scope.status_code == 422
    assert bad_scope.json()["error"]["code"] == "unknown_api_key_scope"

    updated = await client.patch(
        f"/api/v1/api-keys/{record['id']}",
        json={"name": "Renamed", "rate_limit_per_min": 5, "enabled": False},
        headers=headers,
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Renamed"
    assert body["rate_limit_per_min"] == 5
    assert body["enabled"] is False


async def test_key_usage_is_aggregated(client, session_factory, session) -> None:
    headers = await _headers(client, session_factory)
    _, record = await _issue_key(client, headers, quota_tokens=1000)
    session.add_all(
        [
            _usage(
                request_id="req-1",
                api_key_id=uuid.UUID(record["id"]),
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
            ),
            _usage(
                request_id="req-2",
                api_key_id=uuid.UUID(record["id"]),
                input_tokens=4,
                output_tokens=1,
                total_tokens=5,
                error_code="provider_timeout",
            ),
        ]
    )
    await session.commit()

    response = await client.get(f"/api/v1/api-keys/{record['id']}/usage", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["requests"] == 2
    assert body["total_tokens"] == 20
    assert body["error_count"] == 1
    assert body["quota_remaining_tokens"] == 980


async def test_key_deletion_frees_the_prefix(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    _, record = await _issue_key(client, headers)
    deleted = await client.delete(f"/api/v1/api-keys/{record['id']}", headers=headers)
    assert deleted.status_code == 200
    assert deleted.json()["status"] == "deleted"
    assert (
        await client.get(f"/api/v1/api-keys/{record['id']}", headers=headers)
    ).status_code == 404


async def test_viewer_can_read_but_not_manage_keys(client, session_factory) -> None:
    await create_user(session_factory)
    owner_headers = {"Authorization": f"Bearer {await login(client)}"}
    await _issue_key(client, owner_headers)

    await create_user(session_factory, email="viewer@xerex.ai", role=AdminRole.VIEWER)
    viewer_headers = {"Authorization": f"Bearer {await login(client, 'viewer@xerex.ai')}"}

    assert (await client.get("/api/v1/api-keys", headers=viewer_headers)).status_code == 200
    denied = await client.post("/api/v1/api-keys", json={"name": "nope"}, headers=viewer_headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_role"


async def test_key_actions_are_audited(client, session_factory) -> None:
    headers = await _headers(client, session_factory)
    _, record = await _issue_key(client, headers)
    await client.post(f"/api/v1/api-keys/{record['id']}/revoke", headers=headers)

    logs = (await client.get("/api/v1/audit-logs?page_size=50", headers=headers)).json()
    actions = {entry["action"] for entry in logs["items"]}
    assert {"api_key_created", "api_key_revoked"} <= actions
    created = next(entry for entry in logs["items"] if entry["action"] == "api_key_created")
    assert created["diff"]["prefix"] == record["prefix"]
    assert "secret" not in str(created["diff"])


async def test_key_hashes_are_not_guessable(client, session_factory, session) -> None:
    from app.core.security import hash_api_key

    headers = await _headers(client, session_factory)
    secret, record = await _issue_key(client, headers)
    stored = await session.get(ApiKey, uuid.UUID(record["id"]))
    assert stored is not None
    assert stored.hash == hash_api_key(secret)
    assert stored.hash != secret
    assert stored.prefix in secret
