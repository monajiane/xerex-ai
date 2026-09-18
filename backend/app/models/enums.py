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
    PROVIDER = "provider"
    MODEL = "model"
    ENDPOINT = "endpoint"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


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
