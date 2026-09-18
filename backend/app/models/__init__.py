"""SQLAlchemy models.

Importing this package registers every table on ``Base.metadata`` so Alembic
autogenerate can see the full schema. Identifiers stay English (PROMPT.md
section 10); nothing here is user facing.
"""

from app.models.audit import AuditLog
from app.models.health import HealthCheck
from app.models.identity import AdminUser, RefreshToken
from app.models.platform import Setting
from app.models.providers import Model, ModelEndpoint, Provider, ProviderCredential
from app.models.routing import RoutingRule
from app.models.usage import ApiKey, UsageDailyRollup, UsageRecord

__all__ = [
    "AdminUser",
    "ApiKey",
    "AuditLog",
    "HealthCheck",
    "Model",
    "ModelEndpoint",
    "Provider",
    "ProviderCredential",
    "RefreshToken",
    "RoutingRule",
    "Setting",
    "UsageDailyRollup",
    "UsageRecord",
]
