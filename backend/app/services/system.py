"""System information, capability flags and the delivery roadmap.

Capability flags let the Persian admin panel be honest about what is implemented:
``implemented`` renders a working screen, ``placeholder`` renders a clearly marked
«در گام بعدی» screen that lists the planned API contract.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.core.config import settings
from app.health.state import uptime_seconds
from app.schemas.system import (
    Capability,
    LocalizationInfo,
    PlannedEndpoint,
    RoadmapModule,
    RoadmapResponse,
    SystemInfo,
)

# (module key, milestone, state, [(method, path, summary)])
_MODULES: tuple[tuple[str, str, str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        "auth",
        "M1",
        "implemented",
        (
            ("GET", "/api/v1/auth/bootstrap-status", "Whether the first owner must be created."),
            ("POST", "/api/v1/auth/bootstrap", "Create the first owner account."),
            ("POST", "/api/v1/auth/login", "Exchange credentials for a session."),
            ("POST", "/api/v1/auth/refresh", "Rotate the refresh token."),
            ("POST", "/api/v1/auth/logout", "Revoke the current session."),
            ("GET", "/api/v1/auth/me", "Read the authenticated administrator."),
        ),
    ),
    ("health", "M1", "implemented", (("GET", "/api/v1/health", "System component health."),)),
    ("dashboard", "M1", "implemented", (("GET", "/api/v1/dashboard/summary", "KPI aggregates."),)),
    (
        "admin_users",
        "M1",
        "implemented",
        (
            ("GET", "/api/v1/admin-users", "List administrators."),
            ("POST", "/api/v1/admin-users", "Create an administrator."),
            ("PATCH", "/api/v1/admin-users/{user_id}", "Update role or status."),
        ),
    ),
    (
        "settings",
        "M1",
        "implemented",
        (
            ("GET", "/api/v1/settings", "Read platform settings."),
            ("PUT", "/api/v1/settings/{key}", "Update a platform setting."),
        ),
    ),
    (
        "audit_logs",
        "M1",
        "implemented",
        (("GET", "/api/v1/audit-logs", "Administrative audit trail."),),
    ),
    (
        "providers",
        "M2",
        "implemented",
        (
            ("GET", "/api/v1/providers", "List configured providers."),
            ("POST", "/api/v1/providers", "Register a provider."),
            ("PATCH", "/api/v1/providers/{provider_id}", "Update a provider."),
            ("DELETE", "/api/v1/providers/{provider_id}", "Remove a provider."),
            ("POST", "/api/v1/providers/{provider_id}/test", "Test connectivity."),
        ),
    ),
    (
        "provider_credentials",
        "M2",
        "implemented",
        (
            ("GET", "/api/v1/providers/{provider_id}/credentials", "List credentials."),
            ("POST", "/api/v1/providers/{provider_id}/credentials", "Store an encrypted secret."),
            ("POST", "/api/v1/credentials/{credential_id}/verify", "Verify a credential."),
            ("DELETE", "/api/v1/credentials/{credential_id}", "Delete a credential."),
        ),
    ),
    (
        "models",
        "M3",
        "implemented",
        (
            ("GET", "/api/v1/models", "List registered models."),
            ("POST", "/api/v1/models/discover", "Discover models from a provider."),
            ("POST", "/api/v1/models/{model_id}/test", "Run a model test prompt."),
            ("PATCH", "/api/v1/models/{model_id}", "Update model metadata or pricing."),
        ),
    ),
    (
        "api_keys",
        "M4",
        "implemented",
        (
            ("GET", "/api/v1/api-keys", "List downstream API keys."),
            ("POST", "/api/v1/api-keys", "Issue a key (secret returned once)."),
            ("DELETE", "/api/v1/api-keys/{key_id}", "Revoke a key."),
        ),
    ),
    (
        "gateway",
        "M4",
        "implemented",
        (
            ("POST", "/v1/chat/completions", "OpenAI-compatible chat completion."),
            ("POST", "/v1/embeddings", "OpenAI-compatible embeddings."),
            ("GET", "/v1/models", "OpenAI-compatible model list."),
        ),
    ),
    (
        "routing",
        "M5",
        "implemented",
        (
            ("GET", "/api/v1/routing/strategies", "Advertised routing strategies."),
            ("GET", "/api/v1/routing/rules", "List routing rules."),
            ("POST", "/api/v1/routing/rules", "Create a routing rule."),
            ("POST", "/api/v1/routing/simulate", "Dry-run a routing decision."),
        ),
    ),
    (
        "provider_health",
        "M5",
        "implemented",
        (
            ("GET", "/api/v1/health/providers", "Health per provider and credential."),
            ("GET", "/api/v1/health/observations", "Health observation history."),
            ("POST", "/api/v1/health/checks", "Run a health check now."),
        ),
    ),
    (
        "usage",
        "M6",
        "implemented",
        (
            ("GET", "/api/v1/usage/summary", "Aggregated usage, cost and latency."),
            ("GET", "/api/v1/usage/breakdown", "Usage grouped by provider, model or key."),
            ("GET", "/api/v1/usage/export", "CSV/JSON export (Latin digits, ISO-8601)."),
            ("POST", "/api/v1/usage/rollups/rebuild", "Rebuild one day of rollups."),
        ),
    ),
    (
        "request_logs",
        "M6",
        "implemented",
        (
            ("GET", "/api/v1/usage/requests", "Request log with filters and paging."),
            (
                "GET",
                "/api/v1/usage/requests/{request_id}",
                "One request with every upstream attempt.",
            ),
        ),
    ),
)

_CAPABILITY_STATES = {"implemented": "implemented", "planned": "planned"}


def capabilities() -> list[Capability]:
    return [
        Capability(
            key=key,
            state=state,  # type: ignore[arg-type]
            milestone=milestone,
            api_prefix="/v1" if key == "gateway" else "/api/v1",
        )
        for key, milestone, state, _ in _MODULES
    ]


def roadmap() -> RoadmapResponse:
    modules = [
        RoadmapModule(
            key=key,
            milestone=milestone,
            state=state,  # type: ignore[arg-type]
            endpoints=[
                PlannedEndpoint(
                    method=method,
                    path=path,
                    summary=summary,
                    milestone=milestone,
                    state=state,  # type: ignore[arg-type]
                )
                for method, path, summary in endpoints
            ],
        )
        for key, milestone, state, endpoints in _MODULES
    ]
    return RoadmapResponse(current_milestone=settings.milestone, modules=modules)


def system_info() -> SystemInfo:
    return SystemInfo(
        name=settings.app_name,
        version=settings.app_version,
        milestone=settings.milestone,
        environment=settings.environment,
        api_version="v1",
        started_at=datetime.fromtimestamp(_started_at(), tz=UTC),
        uptime_seconds=uptime_seconds(),
        localization=LocalizationInfo(
            default_locale=settings.default_locale,
            supported_locales=settings.supported_locales,
            default_timezone=settings.default_timezone,
        ),
        capabilities=capabilities(),
    )


def _started_at() -> float:
    from app.health.state import started_at

    return started_at()
