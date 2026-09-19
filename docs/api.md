# Xerex AI — API reference (milestone M5)

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
| 403 | `account_inactive`, `insufficient_role`, `permission_denied`, `bootstrap_disabled`, `role_escalation_not_allowed` |
| 404 | `not_found`, `route_not_found`, `provider_not_found`, `credential_not_found`, `model_not_found`, `endpoint_not_found` |
| 409 | `conflict`, `bootstrap_closed`, `email_taken`, `credential_label_duplicate`, `model_name_duplicate`, `credential_missing` |
| 422 | `request_validation_failed`, `validation_failed`, `unknown_setting`, `invalid_setting_value`, `setting_read_only`, `password_too_short`, `cannot_suspend_self`, `owner_role_protected`, `cannot_change_own_role`, `base_url_required`, `endpoint_path_invalid` |
| 502 | any upstream `provider_*` code (discovery and gateway calls, with `details.upstream_status`) |
| 500 | `internal_error`, `credential_decryption_failed` (stored secret cannot be decrypted — the deployment encryption key changed) |

### Upstream provider failure codes

A failed probe is **not** an HTTP error: `POST /providers/{provider_id}/test` and
`POST …/credentials/{credential_id}/verify` answer `200` with `ok: false` plus one of
these stable codes, so the panel can explain the failure in Persian:

| Code | Meaning | Retryable |
| --- | --- | --- |
| `credential_missing` | The provider has no credential to probe | no |
| `provider_unauthorized` | Upstream answered `401` | no |
| `provider_forbidden` | Upstream answered `403` | no |
| `provider_bad_request` | Upstream answered `400` | no |
| `provider_unprocessable` | Upstream answered `422` | no |
| `provider_request_too_large` | Upstream answered `413` | no |
| `provider_model_not_found` | Upstream answered `404` | no |
| `provider_rate_limited` | Upstream answered `429` (`retry_after_seconds` in `details`) | yes |
| `provider_timeout` | No answer inside `timeout_ms` | yes |
| `provider_unavailable` | Upstream answered `5xx` | yes |
| `provider_unreachable` | DNS/TCP/TLS failure | yes |
| `provider_unexpected_response` | Body did not match the documented shape | no |
| `provider_base_url_missing` | No base URL configured | no |
| `provider_discovery_unsupported` · `provider_chat_unsupported` · `provider_streaming_unsupported` · `provider_embeddings_unsupported` | The provider kind cannot do it | no |
| `provider_error` | Anything else | no |
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
{
  "requires_bootstrap": true,
  "bootstrap_enabled": true,
  "admin_user_count": 0,
  "bootstrap_allowed": true
}
```

* `requires_bootstrap` — the data: no owner account exists yet.
* `bootstrap_enabled` — the effective `XEREX_BOOTSTRAP_ENABLED` value (explicit value,
  otherwise *enabled in development/test, disabled in staging/production*).
* `bootstrap_allowed` — `requires_bootstrap && bootstrap_enabled`; the panel shows the
  first-run screen only when this is true, otherwise the sign-in screen with an
  explanation.

### `POST /api/v1/auth/bootstrap`

Creates the first **owner** account. Available only while `admin_user_count == 0`.

```json
{ "email": "owner@example.com", "password": "at-least-10-chars", "full_name": "…" }
```

`201` → `{ "user": AdminUser, "tokens": TokenPair }`. Afterwards the endpoint answers
`409 bootstrap_closed`; when the switch is off it answers `403 bootstrap_disabled`
before any write. The refresh token is also set as an `HttpOnly` cookie.

### `POST /api/v1/auth/login`

```json
{ "email": "owner@example.com", "password": "…" }
```

`200` → `{ "user": AdminUser, "tokens": TokenPair }`.
Rate limited per `ip:email` (`XEREX_LOGIN_RATE_LIMIT_ATTEMPTS`, default 10 per 5 min) →
`429 login_rate_limited`. The `ip` in that key is the *resolved* client address: the
direct peer, or the first untrusted hop in `X-Forwarded-For` when the peer is listed in
`XEREX_TRUSTED_PROXIES`. Failed attempts are audited with `isolated=true` so the entry
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
`admin` | `operator` | `viewer`. Owner accounts cannot be created this way
(`role_escalation_not_allowed` — only an owner may grant `owner`), an owner cannot be
downgraded (`owner_role_protected`), nobody can change their own role
(`cannot_change_own_role`) and an administrator cannot suspend themselves
(`cannot_suspend_self`).

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

## Providers *(M2)*

Providers are stored rows (`providers` table). No provider row is created by the
platform: an administrator adds each one, including its base URL.

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/providers` | all authenticated | `?page&page_size&search&enabled&kind&order_by` (`order_by`: `priority` default, `name`, `created_at`, `-created_at`) |
| `POST` | `/api/v1/providers` | owner, admin | `slug` is derived from `name` when omitted and de-duplicated (`-2`, `-3`, …) |
| `GET` | `/api/v1/providers/{provider_id}` | all authenticated | |
| `PATCH` | `/api/v1/providers/{provider_id}` | owner, admin | Only real changes are written and audited |
| `DELETE` | `/api/v1/providers/{provider_id}` | owner, admin | Cascades to credentials, models and endpoints |
| `GET` | `/api/v1/providers/{provider_id}/delete-impact` | all authenticated | Counts shown in the Persian confirmation dialog |
| `POST` | `/api/v1/providers/{provider_id}/test` | owner, admin, operator | `?credential_id` to probe one specific key; defaults to the provider default |

`ProviderRead` carries live counts (`credential_count`, `model_count`) and the
rolled-up `health_status`, so the panel never has to fake a number.

```json
{
  "id": "5b6c…",
  "slug": "openai-primary",
  "name": "OpenAI Primary",
  "kind": "openai",
  "base_url": "https://api.openai.com/v1",
  "enabled": true,
  "priority": 10,
  "weight": 100,
  "timeout_ms": 30000,
  "max_retries": 2,
  "health_status": "healthy",
  "credential_count": 1,
  "model_count": 3,
  "created_at": "2026-09-19T08:00:00Z",
  "updated_at": "2026-09-19T08:00:00Z"
}
```

---

## Provider credentials *(M2)*

Secrets are encrypted with AES-256-GCM before they are written
(`XEREX_CREDENTIALS_ENCRYPTION_KEY`) and are **never** returned by any endpoint: reads
expose a masked `key_hint` such as `sk-…cdefghijkl`.

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/providers/{provider_id}/credentials` | all authenticated | Paginated |
| `POST` | `/api/v1/providers/{provider_id}/credentials` | owner, admin | `409 credential_label_duplicate` on a duplicate label |
| `PATCH` | `…/credentials/{credential_id}` | owner, admin | Label and status only — never the secret |
| `POST` | `…/credentials/{credential_id}/rotate` | owner, admin | Replaces the ciphertext in place and resets the status to `unverified` |
| `POST` | `…/credentials/{credential_id}/verify` | owner, admin, operator | Probes the key, updates `status`, `last_verified_at`, `last_error_code` and the health history |
| `DELETE` | `…/credentials/{credential_id}` | owner, admin | Endpoints bound to the key fall back to the provider default (`ON DELETE SET NULL`) |
| `GET` | `/api/v1/providers/{provider_id}/default-credential` | all authenticated | The credential an unbound endpoint would use, or `null` |

A credential of another provider is not reachable through a mismatched path — the
pair is validated and answers `404 credential_not_found`.

---

## Routing *(M5)*

«مسیریابی هوشمند» decides *which* provider answers a request. The ordering itself is a
pure function (:mod:`app.router.engine`) used both by live traffic and by the simulator,
so a simulated decision cannot disagree with reality.

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/routing/strategies` | all authenticated | Strategy catalogue |
| `GET` | `/api/v1/routing/rules` | all authenticated | `?enabled` |
| `POST` | `/api/v1/routing/rules` | owner, admin | |
| `GET`·`PATCH`·`DELETE` | `/api/v1/routing/rules/{rule_id}` | read / owner, admin | |
| `POST` | `/api/v1/routing/simulate` | all authenticated | Dry run — nothing is sent upstream |

### Strategies

| Strategy | Primary criterion | Explanation |
| --- | --- | --- |
| `priority` | Provider priority (ascending), then weight | Default when no rule matches |
| `weighted` | Weight (descending), healthy providers first | Traffic distribution |
| `round_robin` | Rotation offset | Cycles one request at a time |
| `latency_aware` | Lowest observed latency | Unmeasured candidates rank after measured ones |
| `cost_aware` | Lowest blended price (input + output per 1M) | `null` price ranks last |
| `failover` | Health rank, then priority | Healthy → degraded → unknown → rate-limited → **down** |

Only `down` removes a candidate from the preferred list; everything else is a preference.
A provider that is down is still tried *after* every healthy one, because an imperfect
answer beats no answer — and the usage row records which attempt was used.

### Simulation result

```json
{
  "model": "gpt-4o-mini",
  "strategy": "latency_aware",
  "rule_id": "…", "rule_name": "قاعده چت",
  "candidates": [
    {"provider_name": "OpenAI Primary", "eligible": true, "latency_ms": 180,
     "price_per_1m": 0.75, "estimated_cost": 0.00075,
     "reasons": ["observed_latency_ms=180", "health=healthy"]},
    {"provider_name": "Backup Provider", "eligible": false, "latency_ms": null,
     "reasons": ["excluded_health_down", "no_price_data"]}
  ],
  "selected_provider_id": "…",
  "explanation": ["strategy=latency_aware", "candidates=2", "eligible=1"]
}
```

`reasons` are stable English tokens; the Persian panel translates them
(`applied_latency` → «زمان پاسخ مشاهده‌شده»). Adding a reason is therefore a translation
entry, not a change to the engine.

---

## Upstream health *(M5)*

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/health/providers` | all authenticated | Latest observation + 24h aggregates per provider |
| `GET` | `/api/v1/health/observations` | all authenticated | `?provider_id&target_type&limit` |
| `POST` | `/api/v1/health/checks` | owner, admin, operator | «اجرای بررسی» — probe now (`?provider_id`) |

* A check writes observations for the **provider and its credential** and rolls the
  provider status up; it never mutates the stored configuration.
* `uptime_percent` and `error_rate` are computed from stored rows only; a provider that
  was never checked reports `unknown` with `uptime_percent: null` — never a fabricated
  «سالم».
* A provider without a credential is reported as `credential_missing` / `unknown` rather
  than as a failure of the upstream service.
* The scheduled batch runs the *same* service as the button, and is opt-in:
  `XEREX_HEALTH_SCHEDULER_ENABLED=true` with `XEREX_HEALTH_CHECK_INTERVAL_SECONDS`
  (default `300`). The scheduler starts and stops with the application lifespan.

---

## Public gateway *(M4)*

The public surface is **OpenAI-compatible**, so an existing client only changes its base
URL. It lives outside `/api/v1` and is authenticated with a downstream key
(`Authorization: Bearer xrx_live_...` or `x-api-key`), never with a panel session.

| Method | Path | Scope | Notes |
| --- | --- | --- | --- |
| `POST` | `/v1/chat/completions` | `chat` | `stream: true` returns `text/event-stream` |
| `POST` | `/v1/completions` | `chat` | Legacy text completion, mapped onto chat |
| `POST` | `/v1/embeddings` | `embeddings` | Provider embeddings, one vector per input |
| `GET` | `/v1/models` | `models` | Enabled models only |
| `GET` | `/v1/models/{model_name}` | `models` | Single catalogue entry |
| `GET` | `/v1/info` | any | The calling key, its limits and its consumed tokens |

### Errors

Failures use the OpenAI envelope — not the admin envelope — including validation errors:

```json
{"error": {"message": "This API key exceeded its per-minute request limit.",
           "type": "rate_limit_error", "code": "rate_limit_exceeded",
           "param": null, "request_id": "req_..."}}
```

| Status | Codes |
| --- | --- |
| 401 | `invalid_api_key` (missing, unknown, revoked, expired or disabled) |
| 403 | `insufficient_scope` |
| 404 | `model_not_found` |
| 422 | `invalid_request` |
| 429 | `rate_limit_exceeded` (with `Retry-After`), `quota_exceeded` |
| 5xx | the upstream `provider_*` code, `gateway_deadline_exceeded`, `gateway_disabled` |

### Resolution and failover

* A request names a **model**; the gateway resolves every enabled provider that serves
  it, together with the credential and the endpoint each candidate would use. Nothing is
  invented: a model without an enabled provider is `404 model_not_found`.
* M4 orders candidates by provider `priority` (then `weight`, then model creation time).
  M5 replaces the *ordering* with the routing engine — the candidate model stays.
* Only **retryable** failures fail over (`provider_rate_limited`, `provider_unavailable`,
  `provider_timeout`, …). A `provider_bad_request` stops immediately: retrying a client
  mistake wastes quota.
* A failed upstream call is an **answer**, not an exception: the unit of work commits and
  writes a health observation (429 → `rate_limited`, 401/403/404 → `down`, other → `degraded`),
  so the failure survives in the health history and in the accounting.
* Streaming resolves the model **before** the response starts, so a missing model is a
  status code rather than an error inside the event stream.

### Accounting

One client request produces one `client_requests` row and **one `usage_records` row per
attempt**, each with provider, credential, model, endpoint, tokens, cost and latency. That
is what makes «چرا این درخواست کند بود؟» answerable per credential instead of averaged
away. Cost is computed from the stored per-million prices; unknown prices mean `0`, never
an invented number.

---

## API key administration *(M4)*

| Method | Path | Roles |
| --- | --- | --- |
| `GET` | `/api/v1/api-keys` | all authenticated (`?search&enabled&include_revoked`) |
| `POST` | `/api/v1/api-keys` | owner, admin |
| `GET`·`PATCH` | `/api/v1/api-keys/{key_id}` | read / owner, admin |
| `POST` | `/api/v1/api-keys/{key_id}/revoke` | owner, admin |
| `DELETE` | `/api/v1/api-keys/{key_id}` | owner, admin |
| `GET` | `/api/v1/api-keys/{key_id}/usage` | all authenticated |

* `POST` returns `ApiKeyCreated.secret` **once** — the plaintext key. Only the SHA-256 hash
  and the display prefix (`xrx_live_8f2a`) are stored, and audit entries never contain the
  secret.
* Scopes are `chat`, `embeddings`, `models`; an unknown scope is
  `422 unknown_api_key_scope`.
* «ابطال» sets `revoked_at` and disables the key while keeping its usage history;
  `DELETE` removes the key (and its usage rows) — the panel words the difference.
* `/usage` aggregates the attempt records: requests, input/output/total tokens, cost,
  error count and the remaining quota.

---

## Models *(M3)*

The registry stores one row per model and provider. Rows are created by hand or by
discovery; the platform never invents a model, a price or a context window.

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/models` | all authenticated | `?search&provider_id&enabled&deprecated&order_by` (`name`, `provider`, `created_at`, `-created_at`) |
| `POST` | `/api/v1/models` | owner, admin | Manual registration; creates the default endpoint |
| `GET` | `/api/v1/models/{model_id}` | all authenticated | |
| `PATCH` | `/api/v1/models/{model_id}` | owner, admin | Display name, context window, prices, capabilities, `enabled`, `deprecated` |
| `DELETE` | `/api/v1/models/{model_id}` | owner, admin | Endpoints cascade |
| `POST` | `/api/v1/models/discover` | owner, admin | «کشف مدل‌ها» — see below |
| `POST` | `/api/v1/models/{model_id}/test` | owner, admin, operator | «آزمایش مدل» — one prompt, real token counts |
| `POST` | `/api/v1/models/{model_id}/test/stream` | owner, admin, operator | Same, as Server-Sent Events |

Prices are stored in **USD per million tokens** (`input_price_per_1m`,
`output_price_per_1m`) exactly as entered; `null` means "unknown", never `0`.

### Discovery

`POST /models/discover`

```json
{ "provider_id": "5b6c…", "overwrite_existing": false }
```

The response is the reconciliation result, not just a list:

```json
{
  "provider_id": "5b6c…",
  "provider_name": "OpenAI Primary",
  "discovered": 12,
  "created": 9,
  "updated": 2,
  "skipped": 1,
  "failed": 0,
  "models": [ { "id": "…", "name": "gpt-4o-mini", "…": "…" } ]
}
```

* `discovered` counts what the provider reported; `created`/`updated`/`skipped` say
  what the registry did with it — an administrator can tell "nothing changed" from
  "the provider returned nothing".
* `overwrite_existing: true` refreshes display name, context window, output limit and
  capabilities of rows that already exist.
* A provider without a credential answers `409 credential_missing`; a provider that
  cannot list models answers `422 provider_discovery_unsupported`; a provider error is
  returned as `502` with the classified `provider_*` code.
* The observation is recorded even when the call fails: health history keeps the
  failure in its own transaction, so a rolled-back request cannot hide it.

### Playground

`POST /models/{model_id}/test` returns `ModelTestResult`:

```json
{
  "model_id": "…", "provider_id": "…",
  "latency_ms": 812, "input_tokens": 12, "output_tokens": 34,
  "output_text": "…", "finish_reason": "stop", "error_code": null
}
```

A failing upstream call is **not** an HTTP error: `error_code` carries the classified
`provider_*` code, the latency and health rows are still written, and the audit trail
records `model_tested` with the outcome. The streaming variant emits:

```text
data: {"delta": "سلام"}
data: {"done": true, "latency_ms": 900, "output_tokens": 0, "finish_reason": "stop"}
data: [DONE]
```

`output_tokens: 0` means the provider did not report usage on the stream — the panel
shows «نامشخص» rather than inventing a number.

---

## Model endpoints *(M3)*

«نقاط اتصال مدل» decide the path, method and credential a request leaves through
(one provider can host several, one endpoint can be bound to an explicit credential).

| Method | Path | Roles |
| --- | --- | --- |
| `GET` | `/api/v1/models/{model_id}/endpoints` | all authenticated |
| `POST` | `/api/v1/models/{model_id}/endpoints` | owner, admin |
| `PATCH` | `/api/v1/models/{model_id}/endpoints/{endpoint_id}` | owner, admin |
| `DELETE` | `/api/v1/models/{model_id}/endpoints/{endpoint_id}` | owner, admin |

* `path` must start with `/` (`422 endpoint_path_invalid`) and is relative to the
  provider base URL; the Gemini family uses `/models/{model}:generateContent`.
* `credential_id: null` means "use the provider default credential".
* A credential that belongs to another provider is rejected (`404 credential_not_found`),
  and an endpoint of another model is not reachable through a mismatched path.

---

## Usage and request logs *(M6)*

«مصرف» and «گزارش درخواست‌ها» read the stored attempt rows. Aggregates are summed
**per attempt**, because that is what the provider actually did — one downstream request
can fan out into several upstream calls, and per-credential accountability depends on it.

| Method | Path | Roles | Notes |
| --- | --- | --- | --- |
| `GET` | `/api/v1/usage/summary` | all authenticated | Totals + time series (`?interval=hour\|day\|week\|month`) |
| `GET` | `/api/v1/usage/breakdown` | all authenticated | `?dimension=provider\|model\|api_key` |
| `GET` | `/api/v1/usage/requests` | all authenticated | `?state&error_code&search&page&page_size` |
| `GET` | `/api/v1/usage/requests/{request_id}` | all authenticated | The request **and every attempt** |
| `GET` | `/api/v1/usage/export` | all authenticated | `?format=csv\|json`, one row per attempt |
| `POST` | `/api/v1/usage/rollups/rebuild` | owner, admin | `?day=YYYY-MM-DD`, idempotent |

All six accept the same filter set: `date_from`, `date_to` (inclusive ISO-8601 dates),
`provider_id`, `model_id`, `api_key_id`. The window defaults to the last seven days when
it is omitted.

### Dates and numbers

* The API speaks **ISO-8601 (Gregorian)**: it is a technical contract, and the Persian
  panel converts Jalali input (`۱۴۰۵/۰۶/۲۸`) at its edge, in
  `frontend/src/lib/locale/jalali.ts`.
* Every count, cost and latency is a stored value; there is no estimation.
  `UsageTotals.p95_latency_ms` is computed from the ordered rows, while a series bucket
  reports `avg_latency_ms` — the field name states what is actually computed.
* `error_rate` is `errors / requests` for the same window, `0.0` when the window is empty.

### Summary

```json
{
  "totals": {
    "requests": 1240, "input_tokens": 480000, "output_tokens": 152000,
    "total_tokens": 632000, "cost": 1.23, "p95_latency_ms": 1800,
    "avg_latency_ms": 420, "error_rate": 0.032, "error_count": 40
  },
  "series": {
    "interval": "day",
    "points": [
      {"bucket": "2026-09-19T00:00:00Z", "requests": 440, "tokens": 232000,
       "cost": 0.43, "error_rate": 0.05, "avg_latency_ms": 383}
    ]
  },
  "range_start": "2026-09-13T00:00:00Z",
  "range_end": "2026-09-19T23:59:59Z",
  "generated_at": "2026-09-19T08:00:00Z"
}
```

Time buckets are computed **per backend**: `date_trunc` on PostgreSQL, the equivalent
`strftime`/`date` expression on SQLite (used by the test suite). `week` always starts on
a Monday on both, so a weekly chart does not shift between deployments.

### Request log

One row per downstream request; `state` is `succeeded`, `failed` or `pending`, and
`attempt_count` makes failover visible at a glance. The detail endpoint returns the same
row plus `attempts[]` — one entry per upstream call with provider, model, credential
label, endpoint path, status code, error code, tokens, cost and latency. Provider,
model and key names are joined from the stored foreign keys, so a deleted provider shows
`—` instead of an empty cell.

### Exports

`GET /api/v1/usage/export?format=csv` streams one row per attempt with
`Content-Disposition: attachment`, an `X-Row-Count` header, UTF-8 **and a BOM**, so Excel
opens Persian labels (`سرویس پشتیبانی`) correctly. `format=json` returns the same rows as
JSON for automation. Exports are capped at 50 000 rows (`EXPORT_ROW_LIMIT`) so a large
window cannot exhaust memory, and they honour the same filters as the screens.

### Rollups

`POST /api/v1/usage/rollups/rebuild` recomputes one day of `usage_daily_rollups` from the
stored attempts. It is idempotent (one row per day and dimension), which is what a
retention job needs.

---

## Reference catalogs

* `GET /api/v1/catalog/providers` — the provider kinds the platform supports
  (`openai`, `anthropic`, `google`, `deepseek`, `qwen`, `openai_compatible`) with
  default base URL, auth scheme and capability flags. `implemented: true` since M2 —
  the registration form reads its defaults from here.
* `GET /api/v1/catalog/routing-strategies` — `priority`, `weighted`, `round_robin`,
  `latency_aware`, `cost_aware`, `failover` with the signals each strategy uses.
  `implemented: false` until M5.

Both return metadata only — no provider is contacted and no traffic exists yet.

---

## Milestone coverage (M1–M6)

Every module of `PROMPT.md` section 5 is delivered; `GET /api/v1/system/roadmap` returns
this table programmatically and reports each module as `implemented` with the endpoint
that serves it — the panel renders what the API claims, and claims nothing else.

| Module | Delivered | Where |
| --- | --- | --- |
| Providers & credentials | M2 | [Providers](#providers-m2) |
| Models, discovery, playground | M3 | [Models](#models-m3) |
| API keys & public gateway | M4 | [Public gateway](#public-gateway-m4), [API key administration](#api-key-administration-m4) |
| Routing rules, simulator, upstream health | M5 | [Routing](#routing-m5), [Upstream health](#upstream-health-m5) |
| Usage analytics, request logs, exports | M6 | [Usage and request logs](#usage-and-request-logs-m6) |
| Authentication, dashboard, users, settings, audit | M1 | this document |

**Already in place for these milestones:** `ModelEndpoint.credential_id` and
`.provider_id` let a routing decision bind an endpoint to a specific credential and/or
a provider other than the model's home provider, `health_checks` carries typed
provider/credential/model/endpoint foreign keys, and `client_requests` +
`usage_records` separate one downstream request from its individual upstream attempts
(tokens and cost per attempt). See the README architecture notes.
