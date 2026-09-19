"""The public gateway engine (M4).

What this module guarantees:

* **Candidate resolution is explicit.** A request names a model; the engine resolves
  every provider that serves it, the credential each candidate would use and the
  endpoint it would call. Milestone M4 orders candidates by provider ``priority``
  (then ``weight``) — the strategy engine of M5 replaces *only* the ordering, not the
  candidate model, so nothing here has to be rewritten.
* **Usage is per attempt.** One ``ClientRequest`` row describes what the client asked
  for; one ``UsageRecord`` per upstream attempt records which provider, credential,
  model and endpoint were tried and what that attempt cost. Failover therefore stays
  auditable instead of being averaged away.
* **Errors are answers, not exceptions.** A failing upstream produces a normal
  OpenAI-compatible error response, so the unit of work commits and the usage record
  survives. Raising would roll the accounting back — exactly the data an operator
  needs when a provider starts failing.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import EncryptionError, decrypt_secret
from app.core.logging import get_logger
from app.health.observations import record_failure_observation
from app.health.targets import HealthTarget
from app.models.enums import ClientRequestState, HealthStatus, RoutingStrategy
from app.models.providers import Model, Provider
from app.models.usage import ApiKey, ClientRequest, UsageRecord
from app.providers.adapters import ChatMessage, ChatResult, UpstreamError, build_adapter
from app.schemas.gateway import ChatCompletionRequest
from app.services.routing import Candidate, RoutingService, resolve_candidates

logger = get_logger(__name__)


class GatewayFailure(Exception):
    """A gateway failure rendered as an OpenAI-compatible error response."""

    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        error_type: str = "xerex_error",
        param: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.error_type = error_type
        self.param = param
        self.retry_after_seconds = retry_after_seconds
        super().__init__(message)

    def as_body(self, request_id: str | None = None) -> dict[str, Any]:
        return {
            "error": {
                "message": self.message,
                "type": self.error_type,
                "code": self.code,
                "param": self.param,
                "request_id": request_id,
            }
        }


@dataclass
class GatewayOutcome:
    """What a gateway call produced: an HTTP status, an OpenAI-shaped body and the
    client-request row that recorded it."""

    status_code: int
    body: dict[str, Any]
    record: ClientRequest | None = None

    @property
    def failed(self) -> bool:
        return "error" in self.body


def estimate_cost(model: Model, input_tokens: int, output_tokens: int) -> Decimal:
    """Cost in USD from the stored per-million prices (``0`` when prices are unknown)."""
    input_price = model.input_price_per_1m or 0
    output_price = model.output_price_per_1m or 0
    total = (Decimal(input_tokens) / Decimal(1_000_000)) * Decimal(str(input_price))
    total += (Decimal(output_tokens) / Decimal(1_000_000)) * Decimal(str(output_price))
    return total.quantize(Decimal("0.00000001"))


def upstream_error_to_failure(exc: UpstreamError) -> GatewayFailure:
    """Map a typed upstream failure onto the OpenAI-compatible error surface."""
    status = exc.status_code or 502
    if not 400 <= status <= 599:
        status = 502
    return GatewayFailure(
        status_code=status,
        code=exc.code,
        message=exc.message,
        error_type="upstream_error",
        retry_after_seconds=exc.retry_after_seconds,
    )


def health_for(error_code: str | None) -> HealthStatus:
    """How an upstream failure should be recorded in the health history."""
    if error_code == "provider_rate_limited":
        return HealthStatus.RATE_LIMITED
    if error_code in {"provider_unauthorized", "provider_forbidden", "provider_model_not_found"}:
        return HealthStatus.DOWN
    if error_code in {"provider_base_url_missing", "credential_missing"}:
        return HealthStatus.UNKNOWN
    return HealthStatus.DEGRADED


class GatewayService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- candidate resolution ------------------------------------------------
    async def resolve_candidates(self, model_name: str) -> list[Candidate]:
        """Raw candidates (provider, credential, endpoint) for ``model_name``."""
        return await resolve_candidates(self.session, model_name)

    async def ordered_candidates(
        self,
        model_name: str,
        *,
        strategy: RoutingStrategy | None = None,
        offset: int = 0,
    ) -> list[Candidate]:
        """Candidates in the order the routing engine chose (M5).

        The engine returns preferred candidates first and the ineligible ones
        afterwards; the gateway keeps both, because a provider whose last observation
        said ``down`` is still a better answer than no answer at all — but it is tried
        last, and the decision is recorded in the usage row.
        """
        ordered, _strategy, _rule = await RoutingService(self.session).decide(
            model_name, strategy=strategy, offset=offset
        )
        return [candidate for candidate, _score in ordered]

    # -- accounting ----------------------------------------------------------
    async def _open_client_request(
        self,
        *,
        request_id: str,
        api_key: ApiKey | None,
        model_name: str,
        streaming: bool,
    ) -> ClientRequest:
        record = ClientRequest(
            request_id=request_id,
            api_key_id=api_key.id if api_key else None,
            requested_model=model_name,
            streaming=streaming,
            state=ClientRequestState.PENDING,
            started_at=datetime.now(UTC),
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def _record_attempt(
        self,
        record: ClientRequest,
        candidate: Candidate,
        *,
        attempt_number: int,
        is_final: bool,
        retryable: bool,
        latency_ms: int,
        status_code: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_code: str | None = None,
        streaming: bool = False,
        api_key: ApiKey | None = None,
    ) -> UsageRecord:
        cost = (
            estimate_cost(candidate.model, input_tokens, output_tokens)
            if error_code is None
            else Decimal(0)
        )
        usage = UsageRecord(
            request_id=record.request_id,
            client_request_id=record.id,
            attempt_number=attempt_number,
            is_final=is_final,
            retryable=retryable,
            api_key_id=api_key.id if api_key else record.api_key_id,
            provider_id=candidate.provider.id,
            credential_id=candidate.credential.id,
            model_id=candidate.model.id,
            endpoint_id=candidate.endpoint.id if candidate.endpoint else None,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost=cost,
            latency_ms=latency_ms,
            status_code=status_code,
            error_code=error_code,
            streaming=streaming,
            created_at=datetime.now(UTC),
        )
        self.session.add(usage)
        await self.session.flush()
        return usage

    @staticmethod
    def _failure_outcome(failure: GatewayFailure, record: ClientRequest | None) -> GatewayOutcome:
        return GatewayOutcome(
            status_code=failure.status_code,
            body=failure.as_body(record.request_id if record else None),
            record=record,
        )

    async def _close_client_request(
        self,
        record: ClientRequest,
        *,
        state: ClientRequestState,
        attempt_count: int,
        latency_ms: int,
        status_code: int,
        input_tokens: int = 0,
        output_tokens: int = 0,
        error_code: str | None = None,
        cost: Decimal | None = None,
    ) -> None:
        record.state = state
        record.attempt_count = attempt_count
        record.latency_ms = latency_ms
        record.final_status_code = status_code
        record.final_error_code = error_code
        record.input_tokens = input_tokens
        record.output_tokens = output_tokens
        record.total_tokens = input_tokens + output_tokens
        record.cost = cost or Decimal(0)
        record.completed_at = datetime.now(UTC)
        await self.session.flush()

    # -- chat ----------------------------------------------------------------
    async def chat_completion(
        self,
        payload: ChatCompletionRequest,
        *,
        api_key: ApiKey | None,
        request_id: str,
    ) -> GatewayOutcome:
        candidates = await self.ordered_candidates(payload.model)
        if not candidates:
            raise GatewayFailure(
                status_code=404,
                code="model_not_found",
                message=(
                    f"No enabled provider serves the model '{payload.model}'. "
                    "Register the model and store a credential first."
                ),
                error_type="invalid_request_error",
                param="model",
            )

        record = await self._open_client_request(
            request_id=request_id,
            api_key=api_key,
            model_name=payload.model,
            streaming=False,
        )
        messages = [
            ChatMessage(role=item.role, content=_content_to_text(item.content))
            for item in payload.messages
        ]
        started = time.monotonic()
        deadline = started + settings.gateway_request_deadline_seconds
        max_tokens = payload.max_tokens or payload.max_completion_tokens or 512
        attempt_number = 0
        last_failure: GatewayFailure | None = None

        for candidate in candidates:
            attempt_number += 1
            attempt_started = time.monotonic()
            if time.monotonic() > deadline:
                break
            adapter = self._build_adapter(candidate)
            try:
                result = await adapter.chat(
                    model=candidate.model.name,
                    messages=messages,
                    temperature=payload.temperature if payload.temperature is not None else 0.2,
                    max_tokens=max_tokens,
                )
            except UpstreamError as exc:
                latency_ms = int((time.monotonic() - attempt_started) * 1000)
                await self._record_attempt(
                    record,
                    candidate,
                    attempt_number=attempt_number,
                    is_final=False,
                    retryable=exc.retryable,
                    latency_ms=latency_ms,
                    status_code=exc.status_code or 502,
                    error_code=exc.code,
                    api_key=api_key,
                )
                last_failure = await self._observe_failure(candidate, exc, latency_ms)
                if not exc.retryable:
                    break
                continue

            latency_ms = int((time.monotonic() - attempt_started) * 1000)
            usage = await self._record_attempt(
                record,
                candidate,
                attempt_number=attempt_number,
                is_final=True,
                retryable=False,
                latency_ms=latency_ms,
                status_code=200,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                api_key=api_key,
            )
            await self._close_client_request(
                record,
                state=ClientRequestState.SUCCEEDED,
                attempt_count=attempt_number,
                latency_ms=int((time.monotonic() - started) * 1000),
                status_code=200,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost=usage.cost,
            )
            await self.session.flush()
            return GatewayOutcome(
                status_code=200,
                body=self._chat_response(payload.model, result, candidate, request_id),
                record=record,
            )

        elapsed = int((time.monotonic() - started) * 1000)
        failure = last_failure or GatewayFailure(
            status_code=504,
            code="gateway_deadline_exceeded",
            message="The request deadline was reached before any provider answered.",
            error_type="timeout_error",
        )
        await self._close_client_request(
            record,
            state=ClientRequestState.FAILED,
            attempt_count=attempt_number,
            latency_ms=elapsed,
            status_code=failure.status_code,
            error_code=failure.code,
        )
        return self._failure_outcome(failure, record)

    async def stream_chat_completion(
        self,
        payload: ChatCompletionRequest,
        *,
        api_key: ApiKey | None,
        request_id: str,
    ) -> AsyncIterator[str]:
        """Yield OpenAI-compatible ``chat.completion.chunk`` SSE frames."""
        candidates = await self.ordered_candidates(payload.model)
        if not candidates:
            raise GatewayFailure(
                status_code=404,
                code="model_not_found",
                message=f"No enabled provider serves the model '{payload.model}'.",
                error_type="invalid_request_error",
                param="model",
            )
        record = await self._open_client_request(
            request_id=request_id,
            api_key=api_key,
            model_name=payload.model,
            streaming=True,
        )
        messages = [
            ChatMessage(role=item.role, content=_content_to_text(item.content))
            for item in payload.messages
        ]
        max_tokens = payload.max_tokens or payload.max_completion_tokens or 512
        started = time.monotonic()
        attempt_number = 0
        last_failure: GatewayFailure | None = None

        for candidate in candidates:
            attempt_number += 1
            if not candidate.streaming_supported:
                continue
            adapter = self._build_adapter(candidate)
            attempt_started = time.monotonic()
            produced = 0
            emitted = False
            try:
                async for delta in adapter.stream_chat(
                    model=candidate.model.name,
                    messages=messages,
                    temperature=payload.temperature if payload.temperature is not None else 0.2,
                    max_tokens=max_tokens,
                ):
                    emitted = True
                    produced += len(delta)
                    yield _chunk_frame(payload.model, request_id, candidate, delta=delta)
            except UpstreamError as exc:
                latency_ms = int((time.monotonic() - attempt_started) * 1000)
                await self._record_attempt(
                    record,
                    candidate,
                    attempt_number=attempt_number,
                    is_final=not exc.retryable,
                    retryable=exc.retryable,
                    latency_ms=latency_ms,
                    status_code=exc.status_code or 502,
                    error_code=exc.code,
                    streaming=True,
                    api_key=api_key,
                )
                last_failure = await self._observe_failure(candidate, exc, latency_ms)
                if emitted:
                    # Bytes already left the gateway; the client must decide, but we
                    # still report the failure in the stream's terminal frame.
                    yield _error_frame(exc.code, exc.message, request_id)
                    break
                if not exc.retryable:
                    break
                continue

            latency_ms = int((time.monotonic() - attempt_started) * 1000)
            usage = await self._record_attempt(
                record,
                candidate,
                attempt_number=attempt_number,
                is_final=True,
                retryable=False,
                latency_ms=latency_ms,
                status_code=200,
                streaming=True,
                api_key=api_key,
            )
            await self._close_client_request(
                record,
                state=ClientRequestState.SUCCEEDED,
                attempt_count=attempt_number,
                latency_ms=int((time.monotonic() - started) * 1000),
                status_code=200,
                cost=usage.cost,
            )
            await self.session.flush()
            yield _chunk_frame(payload.model, request_id, candidate, finish_reason="stop")
            yield "data: [DONE]\n\n"
            return

        failure = last_failure or GatewayFailure(
            status_code=502,
            code="gateway_no_streaming_candidate",
            message="No candidate provider can serve this model as a stream.",
        )
        await self._close_client_request(
            record,
            state=ClientRequestState.FAILED,
            attempt_count=attempt_number,
            latency_ms=int((time.monotonic() - started) * 1000),
            status_code=failure.status_code,
            error_code=failure.code,
        )
        yield _error_frame(failure.code, failure.message, request_id)
        yield "data: [DONE]\n\n"

    # -- embeddings ----------------------------------------------------------
    async def embeddings(
        self,
        *,
        model_name: str,
        inputs: Sequence[str],
        api_key: ApiKey | None,
        request_id: str,
    ) -> GatewayOutcome:
        candidates = await self.ordered_candidates(model_name)
        if not candidates:
            raise GatewayFailure(
                status_code=404,
                code="model_not_found",
                message=f"No enabled provider serves the model '{model_name}'.",
                error_type="invalid_request_error",
                param="model",
            )
        record = await self._open_client_request(
            request_id=request_id,
            api_key=api_key,
            model_name=model_name,
            streaming=False,
        )
        started = time.monotonic()
        attempt_number = 0
        last_failure: GatewayFailure | None = None
        for candidate in candidates:
            attempt_number += 1
            adapter = self._build_adapter(candidate)
            attempt_started = time.monotonic()
            try:
                vectors = await adapter.embeddings(model=candidate.model.name, inputs=list(inputs))
            except UpstreamError as exc:
                latency_ms = int((time.monotonic() - attempt_started) * 1000)
                await self._record_attempt(
                    record,
                    candidate,
                    attempt_number=attempt_number,
                    is_final=not exc.retryable,
                    retryable=exc.retryable,
                    latency_ms=latency_ms,
                    status_code=exc.status_code or 502,
                    error_code=exc.code,
                    api_key=api_key,
                )
                last_failure = await self._observe_failure(candidate, exc, latency_ms)
                if not exc.retryable:
                    break
                continue

            latency_ms = int((time.monotonic() - attempt_started) * 1000)
            usage = await self._record_attempt(
                record,
                candidate,
                attempt_number=attempt_number,
                is_final=True,
                retryable=False,
                latency_ms=latency_ms,
                status_code=200,
                api_key=api_key,
            )
            await self._close_client_request(
                record,
                state=ClientRequestState.SUCCEEDED,
                attempt_count=attempt_number,
                latency_ms=int((time.monotonic() - started) * 1000),
                status_code=200,
                cost=usage.cost,
            )
            await self.session.flush()
            return GatewayOutcome(
                status_code=200,
                body={
                    "object": "list",
                    "data": [
                        {"object": "embedding", "index": index, "embedding": vector}
                        for index, vector in enumerate(vectors)
                    ],
                    "model": model_name,
                    "usage": {"prompt_tokens": 0, "total_tokens": 0},
                },
                record=record,
            )

        failure = last_failure or GatewayFailure(
            status_code=502,
            code="provider_error",
            message="No provider could answer the embeddings request.",
        )
        await self._close_client_request(
            record,
            state=ClientRequestState.FAILED,
            attempt_count=attempt_number,
            latency_ms=int((time.monotonic() - started) * 1000),
            status_code=failure.status_code,
            error_code=failure.code,
        )
        return self._failure_outcome(failure, record)

    # -- preflight -----------------------------------------------------------
    async def assert_servable(self, model_name: str) -> None:
        """Fail *before* a streaming response starts, so the client gets a status code.

        The deadline for delivery is one thing; the promise that a model can be served
        at all is another, and it is checked here with the same resolver the stream
        uses — no second code path, no duplicated rules.
        """
        if not await self.ordered_candidates(model_name):
            raise GatewayFailure(
                status_code=404,
                code="model_not_found",
                message=f"No enabled provider serves the model '{model_name}'.",
                error_type="invalid_request_error",
                param="model",
            )

    # -- catalogue -----------------------------------------------------------
    async def list_models(self) -> dict[str, Any]:
        """OpenAI-compatible ``GET /v1/models`` — enabled models only, no invention."""
        statement = (
            select(Model, Provider)
            .join(Provider, Provider.id == Model.provider_id)
            .where(Model.enabled.is_(True), Provider.enabled.is_(True))
            .order_by(Model.name.asc())
        )
        rows = (await self.session.execute(statement)).all()
        return {
            "object": "list",
            "data": [
                {
                    "id": model.name,
                    "object": "model",
                    "created": int(model.created_at.timestamp()),
                    "owned_by": provider.slug,
                    "context_window": model.context_window,
                }
                for model, provider in rows
            ],
        }

    # -- helpers -------------------------------------------------------------
    def _build_adapter(self, candidate: Candidate):
        try:
            secret = decrypt_secret(candidate.credential.encrypted_secret)
        except EncryptionError as exc:  # pragma: no cover - deployment key mismatch
            raise GatewayFailure(
                status_code=500,
                code="credential_decryption_failed",
                message="The stored provider credential could not be decrypted.",
            ) from exc
        return build_adapter(
            kind=candidate.provider.kind,
            base_url=candidate.provider.base_url,
            secret=secret,
            timeout_ms=candidate.provider.timeout_ms,
        )

    async def _observe_failure(
        self, candidate: Candidate, exc: UpstreamError, latency_ms: int
    ) -> GatewayFailure:
        status = health_for(exc.code)
        await record_failure_observation(
            HealthTarget.provider(candidate.provider.id),
            HealthTarget.credential(candidate.credential.id, provider_id=candidate.provider.id),
            HealthTarget.model(candidate.model.id, provider_id=candidate.provider.id),
            status=status,
            provider_id=candidate.provider.id,
            latency_ms=latency_ms,
            status_code=exc.status_code,
            error_code=exc.code,
        )
        return upstream_error_to_failure(exc)

    @staticmethod
    def _chat_response(
        model_name: str,
        result: ChatResult,
        candidate: Candidate,
        request_id: str,
    ) -> dict[str, Any]:
        return {
            "id": f"chatcmpl-{request_id}",
            "object": "chat.completion",
            "created": int(datetime.now(UTC).timestamp()),
            "model": model_name,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result.text},
                    "finish_reason": result.finish_reason or "stop",
                }
            ],
            "usage": {
                "prompt_tokens": result.input_tokens,
                "completion_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
            },
            "xerex": {
                "provider_id": str(candidate.provider.id),
                "provider_slug": candidate.provider.slug,
                "credential_id": str(candidate.credential.id),
                "endpoint_id": str(candidate.endpoint.id) if candidate.endpoint else None,
                "request_id": request_id,
            },
        }


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content)


def _chunk_frame(
    model_name: str,
    request_id: str,
    candidate: Candidate,
    *,
    delta: str | None = None,
    finish_reason: str | None = None,
) -> str:
    payload: dict[str, Any] = {
        "id": f"chatcmpl-{request_id}",
        "object": "chat.completion.chunk",
        "created": int(datetime.now(UTC).timestamp()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "delta": ({"role": "assistant", "content": delta} if delta is not None else {}),
                "finish_reason": finish_reason,
            }
        ],
    }
    if finish_reason is not None:
        payload["xerex"] = {
            "provider_id": str(candidate.provider.id),
            "credential_id": str(candidate.credential.id),
            "request_id": request_id,
        }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _error_frame(code: str, message: str, request_id: str) -> str:
    payload = {
        "error": {
            "message": message,
            "type": "upstream_error",
            "code": code,
            "request_id": request_id,
        }
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


__all__ = [
    "Candidate",
    "GatewayFailure",
    "GatewayService",
    "estimate_cost",
    "health_for",
    "upstream_error_to_failure",
]
