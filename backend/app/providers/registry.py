"""Provider adapter registry.

M1 ships the registry and the capability metadata only: it lets the admin panel
know which upstream providers the platform will support, without pretending that
provider connectivity already exists. Concrete adapters land in M2.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.enums import ProviderKind


@dataclass(frozen=True)
class ProviderSpec:
    """Static description of an upstream provider family."""

    kind: ProviderKind
    display_name: str
    default_base_url: str
    auth_scheme: str
    supports_model_discovery: bool
    supports_streaming: bool
    supports_embeddings: bool
    implemented: bool = False
    notes: str = ""
    capabilities: tuple[str, ...] = field(default_factory=tuple)


_PROVIDER_SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        kind=ProviderKind.OPENAI,
        display_name="OpenAI",
        default_base_url="https://api.openai.com/v1",
        auth_scheme="bearer",
        supports_model_discovery=True,
        supports_streaming=True,
        supports_embeddings=True,
    ),
    ProviderSpec(
        kind=ProviderKind.ANTHROPIC,
        display_name="Claude",
        default_base_url="https://api.anthropic.com/v1",
        auth_scheme="x-api-key",
        supports_model_discovery=False,
        supports_streaming=True,
        supports_embeddings=False,
    ),
    ProviderSpec(
        kind=ProviderKind.GOOGLE,
        display_name="Gemini",
        default_base_url="https://generativelanguage.googleapis.com/v1beta",
        auth_scheme="api_key_query",
        supports_model_discovery=True,
        supports_streaming=True,
        supports_embeddings=True,
    ),
    ProviderSpec(
        kind=ProviderKind.DEEPSEEK,
        display_name="DeepSeek",
        default_base_url="https://api.deepseek.com/v1",
        auth_scheme="bearer",
        supports_model_discovery=True,
        supports_streaming=True,
        supports_embeddings=False,
    ),
    ProviderSpec(
        kind=ProviderKind.QWEN,
        display_name="Qwen",
        default_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        auth_scheme="bearer",
        supports_model_discovery=True,
        supports_streaming=True,
        supports_embeddings=True,
    ),
    ProviderSpec(
        kind=ProviderKind.OPENAI_COMPATIBLE,
        display_name="OpenAI-compatible",
        default_base_url="",
        auth_scheme="bearer",
        supports_model_discovery=True,
        supports_streaming=True,
        supports_embeddings=True,
        notes="Any endpoint that implements the OpenAI HTTP contract.",
    ),
)


def all_specs() -> tuple[ProviderSpec, ...]:
    return _PROVIDER_SPECS


def get_spec(kind: ProviderKind) -> ProviderSpec | None:
    for spec in _PROVIDER_SPECS:
        if spec.kind == kind:
            return spec
    return None


def catalog() -> list[dict[str, object]]:
    """Serializable catalog used by the admin panel provider form."""
    return [
        {
            "kind": spec.kind.value,
            "display_name": spec.display_name,
            "default_base_url": spec.default_base_url,
            "auth_scheme": spec.auth_scheme,
            "supports_model_discovery": spec.supports_model_discovery,
            "supports_streaming": spec.supports_streaming,
            "supports_embeddings": spec.supports_embeddings,
            "implemented": spec.implemented,
            "notes": spec.notes,
            "milestone": "M2",
        }
        for spec in _PROVIDER_SPECS
    ]
