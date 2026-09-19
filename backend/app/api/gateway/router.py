"""OpenAI-compatible public endpoints (M4).

* ``POST /v1/chat/completions`` — JSON or SSE streaming
* ``POST /v1/completions``     — legacy text completion, mapped onto chat
* ``POST /v1/embeddings``      — provider embeddings
* ``GET  /v1/models``          — enabled models only
* ``GET  /v1/info``            — which key is calling, with what limits

Every response is OpenAI-shaped, including failures, so an existing client can switch
its base URL without a code change. All errors carry a stable English code; the
Persian admin panel is the only place those codes become human text.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.deps import SessionDep
from app.api.gateway.deps import GatewayContext, require_gateway_key
from app.schemas.gateway import ChatCompletionRequest, CompletionRequest, EmbeddingsRequest
from app.services.gateway import GatewayFailure, GatewayService

router = APIRouter(prefix="/v1", tags=["gateway"])

GatewayAuth = Annotated[GatewayContext, Depends(require_gateway_key)]

STREAM_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def failure_response(failure: GatewayFailure, request_id: str | None) -> JSONResponse:
    headers: dict[str, str] = {}
    if failure.retry_after_seconds:
        headers["Retry-After"] = str(int(failure.retry_after_seconds))
    return JSONResponse(
        status_code=failure.status_code,
        content=failure.as_body(request_id),
        headers=headers or None,
    )


@router.post("/chat/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    session: SessionDep,
    context: GatewayAuth,
):
    context.require_scope("chat")
    service = GatewayService(session)

    if payload.stream:
        # Resolve the model before the response starts: a missing model is a status
        # code, not an error buried in the middle of an event stream.
        try:
            await service.assert_servable(payload.model)
        except GatewayFailure as failure:
            return failure_response(failure, context.request_id)
        stream = service.stream_chat_completion(
            payload, api_key=context.api_key, request_id=context.request_id
        )
        return StreamingResponse(stream, media_type="text/event-stream", headers=STREAM_HEADERS)

    outcome = await service.chat_completion(
        payload, api_key=context.api_key, request_id=context.request_id
    )
    return JSONResponse(status_code=outcome.status_code, content=outcome.body)


@router.post("/completions")
async def completions(
    payload: CompletionRequest,
    session: SessionDep,
    context: GatewayAuth,
):
    """Legacy completion surface, expressed as a single user message.

    The upstream call, the usage records and the failover order are exactly those of
    ``/chat/completions`` — only the response envelope differs.
    """
    context.require_scope("chat")
    prompt = payload.prompt if isinstance(payload.prompt, str) else "\n".join(payload.prompt)
    chat_payload = ChatCompletionRequest(
        model=payload.model,
        messages=[{"role": "user", "content": prompt}],
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        stream=False,
    )
    outcome = await GatewayService(session).chat_completion(
        chat_payload, api_key=context.api_key, request_id=context.request_id
    )
    if outcome.failed:
        return JSONResponse(status_code=outcome.status_code, content=outcome.body)

    chat = outcome.body["choices"][0]
    return JSONResponse(
        status_code=200,
        content={
            "id": outcome.body["id"],
            "object": "text_completion",
            "created": outcome.body["created"],
            "model": outcome.body["model"],
            "choices": [
                {
                    "index": 0,
                    "text": chat["message"]["content"],
                    "finish_reason": chat["finish_reason"],
                }
            ],
            "usage": outcome.body["usage"],
            "xerex": outcome.body.get("xerex"),
        },
    )


@router.post("/embeddings")
async def embeddings(
    payload: EmbeddingsRequest,
    session: SessionDep,
    context: GatewayAuth,
):
    context.require_scope("embeddings")
    inputs = payload.input if isinstance(payload.input, list) else [payload.input]
    outcome = await GatewayService(session).embeddings(
        model_name=payload.model,
        inputs=inputs,
        api_key=context.api_key,
        request_id=context.request_id,
    )
    return JSONResponse(status_code=outcome.status_code, content=outcome.body)


@router.get("/models")
async def list_models(session: SessionDep, context: GatewayAuth) -> dict:
    context.require_scope("models")
    return await GatewayService(session).list_models()


@router.get("/models/{model_name}")
async def retrieve_model(model_name: str, session: SessionDep, context: GatewayAuth):
    context.require_scope("models")
    catalogue = await GatewayService(session).list_models()
    for entry in catalogue["data"]:
        if entry["id"] == model_name:
            return entry
    return failure_response(
        GatewayFailure(
            status_code=404,
            code="model_not_found",
            message=f"The model '{model_name}' is not available on this gateway.",
            error_type="invalid_request_error",
            param="model",
        ),
        context.request_id,
    )


@router.get("/info")
async def gateway_info(session: SessionDep, context: GatewayAuth) -> dict:
    """Convenience endpoint for tooling: which key is calling, with what limits."""
    from sqlalchemy import func, select

    from app.models.usage import UsageRecord

    consumed = int(
        (
            await session.execute(
                select(func.coalesce(func.sum(UsageRecord.total_tokens), 0)).where(
                    UsageRecord.api_key_id == context.api_key.id
                )
            )
        ).scalar_one()
    )
    return {
        "key": {
            "id": str(context.api_key.id),
            "prefix": context.api_key.prefix,
            "name": context.api_key.name,
            "scopes": list(context.api_key.scopes or []),
            "rate_limit_per_min": context.api_key.rate_limit_per_min,
            "quota_tokens": context.api_key.quota_tokens,
        },
        "usage": {
            "total_tokens": consumed,
            "remaining_tokens": (
                max(context.api_key.quota_tokens - consumed, 0)
                if context.api_key.quota_tokens is not None
                else None
            ),
        },
        "endpoints": ["/v1/chat/completions", "/v1/completions", "/v1/embeddings", "/v1/models"],
        "request_id": context.request_id or None,
        "milestone": "M4",
    }
