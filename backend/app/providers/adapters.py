"""Upstream provider adapters (M2).

An adapter turns the platform's neutral request shape into the HTTP contract of one
provider family and normalises the answer back. Three families are implemented:

* ``openai_compatible`` — used by OpenAI, DeepSeek, Qwen/DashScope and any gateway
  that speaks the OpenAI HTTP contract;
* ``anthropic`` — Claude's ``/v1/messages`` surface;
* ``google`` — Gemini's ``/v1beta/models/{model}:generateContent`` surface.

Everything here is English and stays English: error codes, log fields and payload
keys are part of the API contract (PROMPT.md section 4).

Design rules
------------

* **No hidden retries.** The adapter performs exactly one upstream call; retry,
  failover and circuit breaking belong to the routing engine (M5), which needs to
  know each individual outcome to record per-attempt usage.
* **No fabricated data.** ``list_models`` returns what the provider reported. When
  a provider cannot list models the adapter raises a typed error instead of
  inventing a catalogue.
* **Secrets never leak into logs.** The secret is only ever placed in headers or
  the query string of the outbound request; error messages include the provider's
  response body, never our credential.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.logging import get_logger
from app.models.enums import ProviderKind

logger = get_logger(__name__)

DEFAULT_TIMEOUT_MS = 30_000
ANTHROPIC_VERSION = "2023-06-01"


# --------------------------------------------------------------------------- #
# Neutral value objects
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class UpstreamModel:
    """One model as reported by the provider."""

    model_id: str
    display_name: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass
class ChatResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class ProbeResult:
    """Outcome of a connectivity/credential probe."""

    ok: bool
    latency_ms: int
    status_code: int | None = None
    error_code: str | None = None
    detail: str | None = None
    model_count: int | None = None


class UpstreamError(Exception):
    """Typed upstream failure with a stable English code.

    ``retryable`` answers "may the router try another candidate?" — it is a property
    of the failure, not of the caller.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
        provider_kind: ProviderKind | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.provider_kind = provider_kind
        super().__init__(message)

    def as_details(self) -> dict[str, Any]:
        details: dict[str, Any] = {}
        if self.status_code is not None:
            details["upstream_status"] = self.status_code
        if self.retry_after_seconds is not None:
            details["retry_after_seconds"] = self.retry_after_seconds
        if self.provider_kind is not None:
            details["provider_kind"] = self.provider_kind.value
        return details


#: HTTP status -> (error code, retryable). 404 is *not* retryable: asking for a model
#: the provider does not have will fail again no matter how often it is retried.
_STATUS_MAP: dict[int, tuple[str, bool]] = {
    400: ("provider_bad_request", False),
    401: ("provider_unauthorized", False),
    403: ("provider_forbidden", False),
    404: ("provider_model_not_found", False),
    408: ("provider_timeout", True),
    413: ("provider_request_too_large", False),
    422: ("provider_unprocessable", False),
    429: ("provider_rate_limited", True),
    500: ("provider_error", True),
    502: ("provider_unavailable", True),
    503: ("provider_unavailable", True),
    504: ("provider_timeout", True),
}


def classify_status(status_code: int) -> tuple[str, bool]:
    if status_code in _STATUS_MAP:
        return _STATUS_MAP[status_code]
    if status_code >= 500:
        return ("provider_unavailable", True)
    return ("provider_error", False)


def _retry_after(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _error_code_from_body(response: httpx.Response) -> str | None:
    """Some providers return a machine-readable code inside the error body."""
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code") or error.get("type") or error.get("status")
        return str(code) if code else None
    if isinstance(error, str):
        return error
    return None


def _summarise_body(response: httpx.Response, *, limit: int = 400) -> str:
    text = response.text or ""
    return text[:limit]


# --------------------------------------------------------------------------- #
# Base adapter
# --------------------------------------------------------------------------- #
class ProviderAdapter:
    """Base class: owns the HTTP client, timeouts and error classification."""

    kind: ProviderKind = ProviderKind.OPENAI_COMPATIBLE

    def __init__(
        self,
        *,
        base_url: str,
        secret: str | None,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        client: httpx.AsyncClient | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = (base_url or "").rstrip("/")
        self.secret = secret
        self.timeout_ms = timeout_ms
        self._client = client
        self._owns_client = client is None
        self.extra_headers = extra_headers or {}

    # -- plumbing ----------------------------------------------------------
    @property
    def timeout(self) -> httpx.Timeout:
        seconds = max(self.timeout_ms, 1) / 1000
        return httpx.Timeout(seconds, connect=min(seconds, 10.0))

    @asynccontextmanager
    async def client(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=False) as client:
            yield client

    def auth_headers(self) -> dict[str, str]:
        return {}

    def headers(self) -> dict[str, str]:
        headers = {"accept": "application/json", "content-type": "application/json"}
        headers.update(self.auth_headers())
        headers.update(self.extra_headers)
        return headers

    def url(self, path: str) -> str:
        if not self.base_url:
            raise UpstreamError(
                "provider_base_url_missing",
                "The provider does not have a base URL configured.",
                provider_kind=self.kind,
            )
        return f"{self.base_url}/{path.lstrip('/')}"

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        async with self.client() as client:
            try:
                response = await client.request(
                    method,
                    self.url(path),
                    headers=self.headers(),
                    json=json_body,
                    params=params,
                    timeout=self.timeout,
                )
            except httpx.TimeoutException as exc:
                raise UpstreamError(
                    "provider_timeout",
                    f"Upstream request timed out after {self.timeout_ms} ms.",
                    retryable=True,
                    provider_kind=self.kind,
                ) from exc
            except httpx.HTTPError as exc:
                raise UpstreamError(
                    "provider_unreachable",
                    f"Upstream provider could not be reached: {exc.__class__.__name__}.",
                    retryable=True,
                    provider_kind=self.kind,
                ) from exc

        if response.status_code >= 400:
            code, retryable = classify_status(response.status_code)
            provider_code = _error_code_from_body(response)
            message = f"Upstream returned {response.status_code}: {_summarise_body(response)}"
            if provider_code:
                message = f"{message} (provider code: {provider_code})"
            raise UpstreamError(
                code,
                message,
                status_code=response.status_code,
                retryable=retryable,
                retry_after_seconds=_retry_after(response),
                provider_kind=self.kind,
            )
        return response

    # -- capability surface ------------------------------------------------
    async def list_models(self) -> list[UpstreamModel]:
        raise UpstreamError(
            "provider_discovery_unsupported",
            f"{self.kind.value} does not expose a model catalogue.",
            provider_kind=self.kind,
        )

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> ChatResult:
        raise UpstreamError(
            "provider_chat_unsupported",
            f"{self.kind.value} chat completions are not implemented.",
            provider_kind=self.kind,
        )

    async def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Yield text deltas. Providers that cannot stream raise a typed error."""
        raise UpstreamError(
            "provider_streaming_unsupported",
            f"{self.kind.value} streaming is not implemented.",
            provider_kind=self.kind,
        )
        yield ""  # pragma: no cover - keeps the signature an async generator

    async def embeddings(self, *, model: str, inputs: Sequence[str]) -> list[list[float]]:
        raise UpstreamError(
            "provider_embeddings_unsupported",
            f"{self.kind.value} embeddings are not implemented.",
            provider_kind=self.kind,
        )

    # -- health ------------------------------------------------------------
    async def probe(self) -> ProbeResult:
        """Cheap connectivity check used by "test connection" and verification.

        A provider that cannot list models still proves connectivity: the probe
        reports the classified failure so the UI can distinguish "wrong key" from
        "provider does not support discovery".
        """
        started = _now_ms()
        try:
            models = await self.list_models()
        except UpstreamError as exc:
            return ProbeResult(
                ok=False,
                latency_ms=_now_ms() - started,
                status_code=exc.status_code,
                error_code=exc.code,
                detail=exc.message,
            )
        return ProbeResult(
            ok=True,
            latency_ms=_now_ms() - started,
            model_count=len(models),
        )


# --------------------------------------------------------------------------- #
# Capability helpers shared by the registry, the discovery job and the gateway
# --------------------------------------------------------------------------- #
#: Providers whose chat endpoint is not the OpenAI-compatible ``/chat/completions``.
_CHAT_PATHS: dict[ProviderKind, str] = {
    ProviderKind.ANTHROPIC: "/messages",
    ProviderKind.GOOGLE: "/models/{model}:generateContent",
}


def default_chat_path(kind: ProviderKind, model_name: str) -> str:
    """Documented dispatch path for a model of this provider family.

    Stored on ``ModelEndpoint`` so an administrator can override it per model; the
    Gemini family embeds the model name in the path, hence the substitution.
    """
    template = _CHAT_PATHS.get(kind, "/chat/completions")
    return template.replace("{model}", model_name)


def supports_streaming(kind: ProviderKind) -> bool:
    from app.providers.registry import get_spec

    return get_spec(kind).supports_streaming


def _now_ms() -> int:
    import time

    return int(time.perf_counter() * 1000)


# --------------------------------------------------------------------------- #
# OpenAI-compatible family
# --------------------------------------------------------------------------- #
class OpenAICompatibleAdapter(ProviderAdapter):
    """``GET /models`` + ``POST /chat/completions`` (+ embeddings)."""

    kind = ProviderKind.OPENAI_COMPATIBLE

    def auth_headers(self) -> dict[str, str]:
        return {"authorization": f"Bearer {self.secret}"} if self.secret else {}

    async def list_models(self) -> list[UpstreamModel]:
        response = await self.request("GET", "models")
        payload = _as_dict(response)
        data = payload.get("data")
        if not isinstance(data, list):
            raise UpstreamError(
                "provider_unexpected_response",
                "The provider returned an unexpected model catalogue shape.",
                provider_kind=self.kind,
            )
        models: list[UpstreamModel] = []
        for entry in data:
            if not isinstance(entry, dict) or not entry.get("id"):
                continue
            models.append(
                UpstreamModel(
                    model_id=str(entry["id"]),
                    display_name=str(entry.get("name") or entry["id"]),
                    context_window=_as_int(entry.get("context_window")),
                    capabilities=({"owned_by": entry["owned_by"]} if entry.get("owned_by") else {}),
                )
            )
        return models

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> ChatResult:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        body.update(extra or {})
        response = await self.request("POST", "chat/completions", json_body=body)
        payload = _as_dict(response)
        choices = payload.get("choices") or []
        text = ""
        finish_reason = None
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            text = str(message.get("content") or "")
            finish_reason = choices[0].get("finish_reason")
        usage = payload.get("usage") or {}
        return ChatResult(
            text=text,
            input_tokens=_as_int(usage.get("prompt_tokens")) or 0,
            output_tokens=_as_int(usage.get("completion_tokens")) or 0,
            finish_reason=finish_reason,
            raw=payload,
        )

    async def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        body.update(extra or {})
        async with (
            self.client() as client,
            client.stream(
                "POST",
                self.url("chat/completions"),
                headers=self.headers(),
                json=body,
                timeout=self.timeout,
            ) as response,
        ):
            if response.status_code >= 400:
                await response.aread()
                code, retryable = classify_status(response.status_code)
                raise UpstreamError(
                    code,
                    f"Upstream returned {response.status_code}: {_summarise_body(response)}",
                    status_code=response.status_code,
                    retryable=retryable,
                    retry_after_seconds=_retry_after(response),
                    provider_kind=self.kind,
                )
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    break
                try:
                    parsed = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                for choice in parsed.get("choices") or []:
                    delta = (choice or {}).get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield str(content)

    async def embeddings(self, *, model: str, inputs: Sequence[str]) -> list[list[float]]:
        response = await self.request(
            "POST", "embeddings", json_body={"model": model, "input": list(inputs)}
        )
        payload = _as_dict(response)
        data = payload.get("data") or []
        vectors: list[list[float]] = []
        for entry in data:
            vector = (entry or {}).get("embedding")
            if isinstance(vector, list):
                vectors.append([float(value) for value in vector])
        if not vectors:
            raise UpstreamError(
                "provider_unexpected_response",
                "The provider returned no embeddings.",
                provider_kind=self.kind,
            )
        return vectors


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #
class AnthropicAdapter(ProviderAdapter):
    kind = ProviderKind.ANTHROPIC

    def auth_headers(self) -> dict[str, str]:
        headers = {"anthropic-version": ANTHROPIC_VERSION}
        if self.secret:
            headers["x-api-key"] = self.secret
        return headers

    async def list_models(self) -> list[UpstreamModel]:
        response = await self.request("GET", "models")
        payload = _as_dict(response)
        data = payload.get("data")
        if not isinstance(data, list):
            raise UpstreamError(
                "provider_unexpected_response",
                "The provider returned an unexpected model catalogue shape.",
                provider_kind=self.kind,
            )
        return [
            UpstreamModel(
                model_id=str(entry["id"]),
                display_name=str(entry.get("display_name") or entry["id"]),
                context_window=_as_int(entry.get("context_window")),
            )
            for entry in data
            if isinstance(entry, dict) and entry.get("id")
        ]

    @staticmethod
    def _split_system(messages: Sequence[ChatMessage]) -> tuple[str | None, list[dict[str, str]]]:
        system_parts = [m.content for m in messages if m.role == "system"]
        conversation = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]
        return ("\n\n".join(system_parts) or None), conversation

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> ChatResult:
        system, conversation = self._split_system(messages)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation,
        }
        if system:
            body["system"] = system
        body.update(extra or {})
        response = await self.request("POST", "messages", json_body=body)
        payload = _as_dict(response)
        text = "".join(
            str(block.get("text") or "")
            for block in (payload.get("content") or [])
            if isinstance(block, dict)
        )
        usage = payload.get("usage") or {}
        return ChatResult(
            text=text,
            input_tokens=_as_int(usage.get("input_tokens")) or 0,
            output_tokens=_as_int(usage.get("output_tokens")) or 0,
            finish_reason=payload.get("stop_reason"),
            raw=payload,
        )

    async def stream_chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        system, conversation = self._split_system(messages)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation,
            "stream": True,
        }
        if system:
            body["system"] = system
        body.update(extra or {})
        async with (
            self.client() as client,
            client.stream(
                "POST",
                self.url("messages"),
                headers=self.headers(),
                json=body,
                timeout=self.timeout,
            ) as response,
        ):
            if response.status_code >= 400:
                await response.aread()
                code, retryable = classify_status(response.status_code)
                raise UpstreamError(
                    code,
                    f"Upstream returned {response.status_code}: {_summarise_body(response)}",
                    status_code=response.status_code,
                    retryable=retryable,
                    provider_kind=self.kind,
                )
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk:
                    continue
                try:
                    parsed = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if parsed.get("type") == "content_block_delta":
                    delta = parsed.get("delta") or {}
                    text = delta.get("text")
                    if text:
                        yield str(text)


# --------------------------------------------------------------------------- #
# Google Gemini
# --------------------------------------------------------------------------- #
class GoogleAdapter(ProviderAdapter):
    kind = ProviderKind.GOOGLE

    def auth_headers(self) -> dict[str, str]:
        # Gemini accepts the key as a query parameter; keeping it out of headers
        # matches the provider contract and keeps ``params`` the single source.
        return {}

    def params(self) -> dict[str, str]:
        return {"key": self.secret} if self.secret else {}

    async def list_models(self) -> list[UpstreamModel]:
        response = await self.request("GET", "models", params=self.params())
        payload = _as_dict(response)
        data = payload.get("models")
        if not isinstance(data, list):
            raise UpstreamError(
                "provider_unexpected_response",
                "The provider returned an unexpected model catalogue shape.",
                provider_kind=self.kind,
            )
        models: list[UpstreamModel] = []
        for entry in data:
            if not isinstance(entry, dict) or not entry.get("name"):
                continue
            methods = entry.get("supportedGenerationMethods") or []
            models.append(
                UpstreamModel(
                    model_id=str(entry["name"]).removeprefix("models/"),
                    display_name=str(entry.get("displayName") or entry["name"]),
                    context_window=_as_int(entry.get("inputTokenLimit")),
                    max_output_tokens=_as_int(entry.get("outputTokenLimit")),
                    capabilities={
                        "methods": [str(method) for method in methods],
                        "generation": "generateContent" in methods,
                        "embeddings": "embedContent" in methods,
                    },
                )
            )
        return models

    @staticmethod
    def _build_body(
        messages: Sequence[ChatMessage], temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        system_parts = [m.content for m in messages if m.role == "system"]
        contents = [
            {
                "role": "model" if m.role == "assistant" else "user",
                "parts": [{"text": m.content}],
            }
            for m in messages
            if m.role != "system"
        ]
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system_parts:
            body["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        return body

    async def chat(
        self,
        *,
        model: str,
        messages: Sequence[ChatMessage],
        temperature: float = 0.2,
        max_tokens: int = 512,
        extra: dict[str, Any] | None = None,
    ) -> ChatResult:
        body = self._build_body(messages, temperature, max_tokens)
        body.update(extra or {})
        response = await self.request(
            "POST", f"models/{model}:generateContent", json_body=body, params=self.params()
        )
        payload = _as_dict(response)
        candidates = payload.get("candidates") or []
        text = ""
        finish_reason = None
        if candidates and isinstance(candidates[0], dict):
            parts = ((candidates[0].get("content") or {}).get("parts")) or []
            text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict))
            finish_reason = candidates[0].get("finishReason")
        usage = payload.get("usageMetadata") or {}
        return ChatResult(
            text=text,
            input_tokens=_as_int(usage.get("promptTokenCount")) or 0,
            output_tokens=_as_int(usage.get("candidatesTokenCount")) or 0,
            finish_reason=finish_reason,
            raw=payload,
        )

    async def embeddings(self, *, model: str, inputs: Sequence[str]) -> list[list[float]]:
        body = {
            "requests": [
                {"model": f"models/{model}", "content": {"parts": [{"text": text}]}}
                for text in inputs
            ]
        }
        response = await self.request(
            "POST", "models:batchEmbedContents", json_body=body, params=self.params()
        )
        payload = _as_dict(response)
        vectors: list[list[float]] = []
        for entry in payload.get("embeddings") or []:
            values = (entry or {}).get("values")
            if isinstance(values, list):
                vectors.append([float(value) for value in values])
        if not vectors:
            raise UpstreamError(
                "provider_unexpected_response",
                "The provider returned no embeddings.",
                provider_kind=self.kind,
            )
        return vectors


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
_ADAPTERS: dict[ProviderKind, type[ProviderAdapter]] = {
    ProviderKind.OPENAI: OpenAICompatibleAdapter,
    ProviderKind.DEEPSEEK: OpenAICompatibleAdapter,
    ProviderKind.QWEN: OpenAICompatibleAdapter,
    ProviderKind.OPENAI_COMPATIBLE: OpenAICompatibleAdapter,
    ProviderKind.ANTHROPIC: AnthropicAdapter,
    ProviderKind.GOOGLE: GoogleAdapter,
}


def adapter_class(kind: ProviderKind) -> type[ProviderAdapter]:
    return _ADAPTERS.get(kind, OpenAICompatibleAdapter)


def build_adapter(
    *,
    kind: ProviderKind,
    base_url: str,
    secret: str | None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    client: httpx.AsyncClient | None = None,
) -> ProviderAdapter:
    """Adapter instance for a provider row. The caller owns the secret's lifetime."""
    return adapter_class(kind)(
        base_url=base_url,
        secret=secret,
        timeout_ms=timeout_ms,
        client=client,
    )


# --------------------------------------------------------------------------- #
# Small parsing helpers
# --------------------------------------------------------------------------- #
def _as_dict(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise UpstreamError(
            "provider_unexpected_response",
            "The provider returned a response that is not valid JSON.",
            status_code=response.status_code,
        ) from exc
    if not isinstance(payload, dict):
        raise UpstreamError(
            "provider_unexpected_response",
            "The provider returned a JSON value that is not an object.",
            status_code=response.status_code,
        )
    return payload


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def supported_kinds() -> Iterable[ProviderKind]:
    return tuple(_ADAPTERS)
