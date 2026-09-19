"""Public gateway contracts (M4).

These shapes follow the OpenAI API on purpose: an existing client can point its base
URL at ``/v1`` without changing code. Field names stay English — the Persian panel
never sees them, and the gateway never returns Persian text (PROMPT.md 4 / 14.11).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MessageRole = Literal["system", "user", "assistant", "tool", "developer"]


class GatewayMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: MessageRole
    content: str | list[dict[str, Any]] | None = None
    name: str | None = None

    @field_validator("content")
    @classmethod
    def _accept_text_parts(cls, value: Any) -> Any:
        """Accept the documented content-part list without inspecting it further."""
        return value


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1, max_length=160)
    messages: list[GatewayMessage] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int | None = Field(default=None, ge=1, le=100_000)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=100_000)
    stream: bool = False
    stop: str | list[str] | None = None
    user: str | None = None


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1, max_length=160)
    prompt: str | list[str] = Field(min_length=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=100_000)
    stream: bool = False


class EmbeddingsRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = Field(min_length=1, max_length=160)
    input: str | list[str] = Field(min_length=1)


class GatewayError(BaseModel):
    """OpenAI-compatible error body (``code`` carries the stable English code)."""

    message: str
    type: str = "xerex_error"
    code: str
    param: str | None = None
    request_id: str | None = None


class GatewayErrorResponse(BaseModel):
    error: GatewayError


__all__ = [
    "ChatCompletionRequest",
    "CompletionRequest",
    "EmbeddingsRequest",
    "GatewayError",
    "GatewayErrorResponse",
    "GatewayMessage",
]
