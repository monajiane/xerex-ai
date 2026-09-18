# Xerex AI — API reference (milestone M1)

* Base URL: `/api/v1` for the admin API, `/v1` for the public gateway (M4).
* All identifiers, field names, error codes and messages are **English**.
* The Persian admin panel translates the stable `error.code` values; it never
  receives Persian text from the API.

## Conventions

| Topic | Rule |
| --- | --- |
| Auth | `Authorization: Bearer <access_token>` (15 minutes) |
| Refresh | `HttpOnly` cookie `xerex_refresh_token`, path `/api/v1/auth`, rotated on every use |
| Pagination | `?page=1&page_size=25`, response `{ items, total, page, page_size }` |
| Correlation | every response carries `X-Request-ID`; the value is echoed from the request when supplied |
| Timestamps | ISO-8601, UTC (`2026-09-18T10:30:00Z`) |
| Numbers | Latin digits; Persian digits exist only in the UI layer |
| Enums | lowercase English values (`openai`, `owner`, `healthy`, `latency_aware`) |

### Error envelope

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "Invalid email or password.",
    "request_id": "req_9f2a1c…",
    "details": { "retry_after_seconds": 12 }
  }
}
```

| HTTP | Typical codes |
| --- | --- |
| 400 | `bad_request` |
| 401 | `authentication_required`, `invalid_credentials`, `token_expired`, `token_invalid`, `token_revoked`, `refresh_token_missing` |
| 403 | `account_inactive`, `insufficient_role`, `permission_denied` |
| 404 | `not_found`, `route_not_found` |
| 409 | `conflict`, `bootstrap_closed`, `email_taken` |
| 422 | `request_validation_failed`, `validation_failed`, `unknown_setting`, `invalid_setting_value`, `setting_read_only`, `password_too_short`, `cannot_suspend_self`, `owner_role_protected` |
| 429 | `login_rate_limited`, `rate_limit_exceeded` |
| 500 | `internal_error`, `encryption_error` |
| 501 | `not_implemented` (planned capabilities, when reachable) |
| 503 | `dependency_unavailable`, `component_down` |

---

## Health

### `GET /health` — liveness

No dependency checks; used by container orchestrators.

```json
{ "status": "ok", "service": "Xerex AI", "version": "0.1.0", "environment": "development" }
```

### `GET /api/v1/health` — readiness

```json
{
  "status": "healthy",
  "service": "Xerex AI",
  "version": "0.1.0",
  "milestone": "M1",
  "environment": "development",
  "checked_at": "2026-09-18T10:30:00Z",
  "uptime_seconds": 913.4,
  "components": [
    { "name": "database", "status": "healthy", "latency_ms": 1.8, "dialect": "postgresql", "version": "PostgreSQL 16.2" },
    { "name": "redis", "status": "healthy", "latency_ms": 2.1, "version": "6.2.14", "required": false }
  ]
}
```

`status` is `healthy`, `degraded` or `down`. When `XEREX_REDIS_REQUIRED=false`
(the default) Redis failures degrade the report instead of failing it, and rate
limiting fails open.

### `GET /api/v1/health/ready`

Same payload; returns **503 `component_down`** when a required component is down.

---

## Authentication

### `GET /api/v1/auth/bootstrap-status`

```json
{ "requires_bootstrap": true, "bootstrap_enabled": true, "admin_user_count": 0 }
```

### `POST /api/v1/auth/bootstrap`

Creates the first **owner** account. Available only while `admin_user_count == 0`.

```json
{ "email": "owner@example.com", "password": "at-least-10-chars", "full_name": "…" }
```

`201` → `{ "user": AdminUser, "tokens": TokenPair }`; afterwards `409 bootstrap_closed`.
The refresh token is also set as an `HttpOnly` cookie.

### `POST /api/v1/auth/login`

```json
{ "email": "owner@example.com", "password": "…" }
```

`200` → `{ "user": AdminUser, "tokens": TokenPair }`.
Rate limited per `ip:email` (`XEREX_LOGIN_RATE_LIMIT_ATTEMPTS`, default 10 per 5 min) →
`429 login_rate_limited`. Failed attempts are audited with `isolated=true` so the entry
survives the rolled-back request.

### `POST /api/v1/auth/refresh`

Uses the `xerex_refresh_token` cookie. The presented token is **single use**: a replay
returns `401 token_revoked`.

### `POST /api/v1/auth/logout`

Revokes the current refresh token and clears the cookie.

### `GET /api/v1/auth/me`

Returns the authenticated administrator.

**AdminUser**

```json
{
  "id": "16940a2c-c660-4887-b08d-86f15cc5d1e1",
  "email": "owner@example.com",
  "full_name": "مدیر سیستم",
  "role": "owner",
  "status": "active",
  "mfa_enabled": false,
  "last_login_at": "2026-09-18T10:00:00Z",
  "created_at": "2026-09-18T09:00:00Z"
}
```

---

## System

### `GET /api/v1/system/info`

Public metadata plus the capability flags the panel uses to mark planned modules.

```json
{
  "name": "Xerex AI",
  "version": "0.1.0",
  "milestone": "M1",
  "environment": "development",
  "api_version": "v1",
  "started_at": "2026-09-18T09:00:00Z",
  "uptime_seconds": 3600.0,
  "localization": {
    "default_locale": "fa",
    "supported_locales": ["fa", "en"],
    "default_timezone": "Asia/Tehran"
  },
  "capabilities": [
    { "key": "dashboard", "state": "implemented", "milestone": "M1", "api_prefix": "/api/v1" },
    { "key": "providers", "state": "planned", "milestone": "M2", "api_prefix": "/api/v1" }
  ]
}
```

`state` ∈ `implemented` | `placeholder` | `planned`.

### `GET /api/v1/system/roadmap` *(authenticated)*

Every module with its milestone and planned endpoints — used by the panel's Persian
placeholder screens (`«در گام بعدی»`) so nothing is faked.

---

## Dashboard

### `GET /api/v1/dashboard/summary` *(authenticated)*

```json
{
  "generated_at": "2026-09-18T10:30:00Z",
  "window": "24h",
  "metrics": [
    { "key": "requests", "value": 0, "unit": "requests", "window": "24h", "available": true },
    { "key": "p95_latency_ms", "value": 0, "unit": "ms", "window": "24h", "available": false }
  ],
  "provider_health": [],
  "top_models": [],
  "counts": { "providers": 0, "enabled_providers": 0, "models": 0, "api_keys": 0, "admin_users": 1 },
  "has_provider_data": false,
  "system_status": "healthy"
}
```

`available: false` means "no samples yet" — the panel renders «نمونه‌ای ثبت نشده»
instead of a misleading `0`. `has_provider_data` is `false` until a provider exists,
so the panel shows the «هنوز ارائه‌دهنده‌ای افزوده نشده است» empty state.

---

## Administrators

| Method | Path | Roles |
| --- | --- | --- |
| `GET` | `/api/v1/admin-users` | owner, admin, operator, viewer |
| `POST` | `/api/v1/admin-users` | owner, admin |
| `PATCH` | `/api/v1/admin-users/{user_id}` | owner, admin |

`POST` body: `{ email, password, full_name?, role }` where role ∈
`admin` | `operator` | `viewer`. Owner accounts cannot be created this way, an owner
cannot be downgraded (`owner_role_protected`) and an administrator cannot suspend
themselves (`cannot_suspend_self`).

---

## Settings

### `GET /api/v1/settings` *(any authenticated role)*

```json
{
  "items": [
    { "key": "ui.default_locale", "value": "fa", "editable": true, "updated_at": null },
    { "key": "ui.numeral_style", "value": "persian", "editable": true, "updated_at": null }
  ],
  "supported_locales": ["fa", "en"],
  "default_locale": "fa"
}
```

Known keys: `ui.default_locale`, `ui.numeral_style`, `ui.theme`, `ui.timezone`,
`ui.sidebar_collapsed`, `notifications.email_enabled`, `notifications.health_alerts`,
`retention.usage_days`, `retention.logs_days`.

### `PUT /api/v1/settings/{key}` *(owner, admin)*

```json
{ "value": "latin" }
```

Validation is key-aware: unsupported locale, unknown time zone, non-positive retention
or a non-boolean flag → `422 invalid_setting_value` with `details.reason`. Unknown keys
→ `422 unknown_setting`. Every accepted change writes an audit entry.

---

## Audit log

### `GET /api/v1/audit-logs?page=1&page_size=50` *(owner, admin)*

```json
{
  "items": [
    {
      "id": "…",
      "actor_email": "owner@example.com",
      "action": "login_succeeded",
      "entity_type": null,
      "entity_id": null,
      "diff": null,
      "ip_address": "127.0.0.1",
      "request_id": "req_…",
      "created_at": "2026-09-18T10:00:00Z"
    }
  ],
  "total": 12, "page": 1, "page_size": 50
}
```

Actions: `login_succeeded`, `login_failed`, `logout`, `token_refreshed`,
`bootstrap_owner_created`, `settings_updated`, `user_created`, `user_updated`,
`user_disabled`.

---

## Reference catalogs

* `GET /api/v1/catalog/providers` — the provider kinds the platform supports
  (`openai`, `anthropic`, `google`, `deepseek`, `qwen`, `openai_compatible`) with
  default base URL, auth scheme and capability flags. `implemented: false` until M2.
* `GET /api/v1/catalog/routing-strategies` — `priority`, `weighted`, `round_robin`,
  `latency_aware`, `cost_aware`, `failover` with the signals each strategy uses.
  `implemented: false` until M5.

Both return metadata only — no provider is contacted and no traffic exists yet.

---

## Planned contracts (M2–M6)

Frozen Pydantic shapes already live in `backend/app/schemas/`, so the panel can be built
against them without redesign:

| Module | Endpoints (planned) |
| --- | --- |
| Providers | `GET/POST /providers`, `PATCH/DELETE /providers/{provider_id}`, `POST /providers/{provider_id}/test` |
| Credentials | `GET/POST /providers/{provider_id}/credentials`, `POST /credentials/{id}/verify`, `DELETE /credentials/{id}` |
| Models | `GET /models`, `POST /models/discover`, `PATCH /models/{model_id}`, `POST /models/{model_id}/test` |
| API keys | `GET/POST /api-keys`, `DELETE /api-keys/{key_id}` (secret returned once) |
| Routing | `GET/POST /routing-rules`, `POST /routing-rules/simulate` |
| Health checks | `GET /health-checks`, `POST /health-checks/run` |
| Usage | `GET /usage/summary`, `GET /usage/export` |
| Request logs | `GET /logs` |
| Gateway | `POST /v1/chat/completions`, `POST /v1/embeddings`, `GET /v1/models` |

`GET /api/v1/system/roadmap` returns this list programmatically.
