"""Provider adapters: request shape, response normalisation and error mapping (M2).

Every upstream is mocked with ``httpx.MockTransport``, so the suite proves the exact
HTTP contract without contacting a real provider and without pretending that a
provider integration was verified end to end.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.models.enums import ProviderKind
from app.providers.adapters import (
    AnthropicAdapter,
    ChatMessage,
    GoogleAdapter,
    OpenAICompatibleAdapter,
    UpstreamError,
    build_adapter,
    classify_status,
)


def client_for(handler) -> httpx.AsyncClient:  # noqa: ANN001
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def json_response(payload: dict, status_code: int = 200, headers: dict | None = None):
    return httpx.Response(status_code, json=payload, headers=headers or {})


# --------------------------------------------------------------------------- #
# OpenAI-compatible family
# --------------------------------------------------------------------------- #
async def test_openai_adapter_lists_models_and_sends_bearer_token() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return json_response({"data": [{"id": "gpt-4o-mini", "owned_by": "openai"}]})

    adapter = build_adapter(
        kind=ProviderKind.OPENAI,
        base_url="https://api.openai.com/v1",
        secret="sk-test-secret",
        client=client_for(handler),
    )
    models = await adapter.list_models()

    assert seen["url"] == "https://api.openai.com/v1/models"
    assert seen["auth"] == "Bearer sk-test-secret"
    assert [model.model_id for model in models] == ["gpt-4o-mini"]
    assert models[0].capabilities == {"owned_by": "openai"}


async def test_openai_adapter_normalises_chat_completion_and_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        assert body["messages"] == [{"role": "user", "content": "سلام"}]
        assert body["stream"] is False
        return json_response(
            {
                "choices": [{"message": {"content": "پاسخ"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7},
            }
        )

    adapter = OpenAICompatibleAdapter(
        base_url="https://api.openai.com/v1",
        secret="sk-test",
        client=client_for(handler),
    )
    result = await adapter.chat(
        model="gpt-4o-mini", messages=[ChatMessage(role="user", content="سلام")]
    )

    assert result.text == "پاسخ"
    assert (result.input_tokens, result.output_tokens, result.total_tokens) == (11, 7, 18)
    assert result.finish_reason == "stop"


async def test_openai_adapter_streams_deltas_and_stops_at_done() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True

        def lines():
            yield b'data: {"choices":[{"delta":{"content":"\xd8\xb3"}}]}\n\n'
            yield b'data: {"choices":[{"delta":{"content":"\xd9\x84\xd8\xa7\xd9\x85"}}]}\n\n'
            yield b"data: [DONE]\n\n"

        return httpx.Response(200, stream=httpx.ByteStream(b"".join(lines())))

    adapter = OpenAICompatibleAdapter(
        base_url="https://api.openai.com/v1", secret="sk-test", client=client_for(handler)
    )
    chunks = [
        chunk
        async for chunk in adapter.stream_chat(
            model="gpt-4o-mini", messages=[ChatMessage(role="user", content="hi")]
        )
    ]
    assert "".join(chunks) == "سلام"


@pytest.mark.parametrize(
    ("status_code", "expected_code", "retryable"),
    [
        (400, "provider_bad_request", False),
        (401, "provider_unauthorized", False),
        (404, "provider_model_not_found", False),
        (429, "provider_rate_limited", True),
        (500, "provider_error", True),
        (503, "provider_unavailable", True),
        (418, "provider_error", False),
    ],
)
def test_http_status_mapping_is_stable(
    status_code: int, expected_code: str, retryable: bool
) -> None:
    assert classify_status(status_code) == (expected_code, retryable)


async def test_openai_adapter_maps_rate_limit_and_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response(
            {"error": {"code": "rate_limit_exceeded", "message": "slow down"}},
            status_code=429,
            headers={"retry-after": "12"},
        )

    adapter = OpenAICompatibleAdapter(
        base_url="https://api.openai.com/v1", secret="sk-test", client=client_for(handler)
    )
    with pytest.raises(UpstreamError) as excinfo:
        await adapter.list_models()

    error = excinfo.value
    assert error.code == "provider_rate_limited"
    assert error.retryable is True
    assert error.retry_after_seconds == 12
    assert error.status_code == 429
    # The provider's own error body is surfaced, our credential never is.
    assert "rate_limit_exceeded" in error.message


async def test_adapter_reports_network_failure_as_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    adapter = OpenAICompatibleAdapter(
        base_url="https://api.openai.com/v1", secret="sk-test", client=client_for(handler)
    )
    # The call surface raises (the router needs the typed failure to fail over) ...
    with pytest.raises(UpstreamError) as excinfo:
        await adapter.list_models()
    assert excinfo.value.code == "provider_unreachable"
    assert excinfo.value.retryable is True
    # ... while ``probe`` folds it into a result for the verification endpoints.
    probe = await adapter.probe()
    assert probe.ok is False and probe.error_code == "provider_unreachable"


async def test_adapter_maps_timeouts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("too slow")

    adapter = OpenAICompatibleAdapter(
        base_url="https://api.openai.com/v1", secret="sk-test", client=client_for(handler)
    )
    with pytest.raises(UpstreamError) as excinfo:
        await adapter.chat(model="gpt-4o-mini", messages=[ChatMessage(role="user", content="hi")])
    assert excinfo.value.code == "provider_timeout"
    assert excinfo.value.retryable is True


async def test_probe_reports_failure_instead_of_raising() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return json_response({"error": {"code": "invalid_api_key"}}, status_code=401)

    adapter = OpenAICompatibleAdapter(
        base_url="https://api.openai.com/v1", secret="sk-bad", client=client_for(handler)
    )
    probe = await adapter.probe()
    assert probe.ok is False
    assert probe.error_code == "provider_unauthorized"
    assert probe.status_code == 401


async def test_adapter_without_base_url_fails_cleanly() -> None:
    adapter = OpenAICompatibleAdapter(base_url="", secret="sk-test")
    with pytest.raises(UpstreamError) as excinfo:
        await adapter.list_models()
    assert excinfo.value.code == "provider_base_url_missing"


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #
async def test_anthropic_adapter_uses_its_own_auth_headers_and_payload_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("x-api-key") == "sk-ant-test"
        assert request.headers.get("anthropic-version")
        assert "authorization" not in request.headers
        body = json.loads(request.content)
        assert body["system"] == "دستور سیستمی"
        assert body["messages"] == [{"role": "user", "content": "سلام"}]
        return json_response(
            {
                "content": [{"type": "text", "text": "پاسخ کلود"}],
                "usage": {"input_tokens": 5, "output_tokens": 9},
                "stop_reason": "end_turn",
            }
        )

    adapter = AnthropicAdapter(
        base_url="https://api.anthropic.com/v1", secret="sk-ant-test", client=client_for(handler)
    )
    result = await adapter.chat(
        model="claude-sonnet-4",
        messages=[
            ChatMessage(role="system", content="دستور سیستمی"),
            ChatMessage(role="user", content="سلام"),
        ],
    )
    assert result.text == "پاسخ کلود"
    assert (result.input_tokens, result.output_tokens) == (5, 9)
    assert result.finish_reason == "end_turn"


# --------------------------------------------------------------------------- #
# Google
# --------------------------------------------------------------------------- #
async def test_google_adapter_passes_key_in_query_and_parses_capabilities() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("key") == "gemini-key"
        return json_response(
            {
                "models": [
                    {
                        "name": "models/gemini-2.0-flash",
                        "displayName": "Gemini 2.0 Flash",
                        "inputTokenLimit": 1_000_000,
                        "outputTokenLimit": 8192,
                        "supportedGenerationMethods": ["generateContent", "embedContent"],
                    }
                ]
            }
        )

    adapter = GoogleAdapter(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        secret="gemini-key",
        client=client_for(handler),
    )
    models = await adapter.list_models()
    assert models[0].model_id == "gemini-2.0-flash"
    assert models[0].context_window == 1_000_000
    assert models[0].capabilities["embeddings"] is True


async def test_google_adapter_builds_generate_content_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "systemInstruction" in body
        assert body["contents"][0]["parts"][0]["text"] == "سلام"
        assert body["generationConfig"]["maxOutputTokens"] == 128
        return json_response(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "پاسخ جمینای"}]}, "finishReason": "STOP"}
                ],
                "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 4},
            }
        )

    adapter = GoogleAdapter(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        secret="gemini-key",
        client=client_for(handler),
    )
    result = await adapter.chat(
        model="gemini-2.0-flash",
        messages=[
            ChatMessage(role="system", content="سیستم"),
            ChatMessage(role="user", content="سلام"),
        ],
        max_tokens=128,
    )
    assert result.text == "پاسخ جمینای"
    assert result.total_tokens == 7
