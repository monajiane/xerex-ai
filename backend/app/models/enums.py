"""Enumerations shared by models and schemas.

Enum *values* are English and stable: they are part of the API contract and are
translated to Persian labels only in the admin panel i18n layer.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


def enum_type(enum_cls: type[StrEnum], name: str, length: int = 32) -> SAEnum:
    """Portable enum column storing member *values* (e.g. ``openai``).

    ``native_enum=False`` keeps the schema portable across PostgreSQL and the
    SQLite used by the test-suite.
    """
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda cls: [member.value for member in cls],  # type: ignore[arg-type]
    )


class AdminRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INVITED = "invited"


class ProviderKind(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    OPENAI_COMPATIBLE = "openai_compatible"


class CredentialStatus(StrEnum):
    UNVERIFIED = "unverified"
    ACTIVE = "active"
    INVALID = "invalid"
    REVOKED = "revoked"


class HealthTargetType(StrEnum):
    """What a health observation is about.

    The routing engine needs provider, credential, model *and* endpoint health
    independently: a provider can be healthy while one of its credentials is rate
    limited and a single endpoint is degraded (PROMPT.md routing section).
    """

    PROVIDER = "provider"
    CREDENTIAL = "credential"
    MODEL = "model"
    ENDPOINT = "endpoint"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    #: Reachable but slow or partially failing.
    DEGRADED = "degraded"
    #: Temporarily rejecting traffic because the upstream quota was hit.
    RATE_LIMITED = "rate_limited"
    DOWN = "down"
    UNKNOWN = "unknown"


class ClientRequestState(StrEnum):
    """Lifecycle of one downstream client request (M4 gateway)."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class RoutingStrategy(StrEnum):
    PRIORITY = "priority"
    WEIGHTED = "weighted"
    ROUND_ROBIN = "round_robin"
    LATENCY_AWARE = "latency_aware"
    COST_AWARE = "cost_aware"
    FAILOVER = "failover"


class AuditAction(StrEnum):
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    TOKEN_REFRESHED = "token_refreshed"
    BOOTSTRAP_OWNER_CREATED = "bootstrap_owner_created"
    SETTINGS_UPDATED = "settings_updated"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DISABLED = "user_disabled"
    # -- M2: providers and credentials
    PROVIDER_CREATED = "provider_created"
    PROVIDER_UPDATED = "provider_updated"
    PROVIDER_DELETED = "provider_deleted"
    PROVIDER_TESTED = "provider_tested"
    CREDENTIAL_CREATED = "credential_created"
    CREDENTIAL_UPDATED = "credential_updated"
    CREDENTIAL_DELETED = "credential_deleted"
    CREDENTIAL_ROTATED = "credential_rotated"
    CREDENTIAL_VERIFIED = "credential_verified"
    # -- M3: models and discovery
    MODEL_CREATED = "model_created"
    MODEL_UPDATED = "model_updated"
    MODEL_DELETED = "model_deleted"
    MODELS_DISCOVERED = "models_discovered"
    ENDPOINT_CREATED = "endpoint_created"
    ENDPOINT_UPDATED = "endpoint_updated"
    ENDPOINT_DELETED = "endpoint_deleted"
    MODEL_TESTED = "model_tested"
    # -- M4: downstream API keys and the gateway
    # -- M5: routing and scheduled health checks
    ROUTING_RULE_CREATED = "routing_rule_created"
    ROUTING_RULE_UPDATED = "routing_rule_updated"
    ROUTING_RULE_DELETED = "routing_rule_deleted"
    ROUTING_SIMULATED = "routing_simulated"
    HEALTH_CHECKS_RUN = "health_checks_run"
    API_KEY_CREATED = "api_key_created"
    API_KEY_UPDATED = "api_key_updated"
    API_KEY_REVOKED = "api_key_revoked"
    API_KEY_DELETED = "api_key_deleted"
