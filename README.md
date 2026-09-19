# Xerex AI

Self-hosted AI management platform: a unified LLM gateway plus an enterprise-grade
administration panel.

> **Language contract — non-negotiable**
>
> | Surface | Language | Direction |
> | --- | --- | --- |
> | Admin panel (the product administrators see) | **Persian (فارسی)** | **RTL** |
> | Secondary panel language | English | LTR |
> | API, database, source code, identifiers, logs, commits | English | — |
>
> The panel is not a translated English product: it is Persian-first and RTL-native.
> The backend is English-native: `provider_id`, `model_endpoint`, `api_key_id` and
> every other identifier stay English in code and in JSON, while the administrator
> sees **«ارائه‌دهنده»**, **«نقطه اتصال مدل»** and **«شناسه کلید API»**.
> See [`PROMPT.md`](./PROMPT.md) for the full specification (section 14 covers the
> Persian/RTL requirements).

---

## Current status — milestone M7

The full-stack foundation is in place (authentication, the database schema for every
planned module, a Persian-first admin shell), **M2** adds the provider and credential
modules (registration, encrypted keys, verification, connectivity tests) and **M3**
adds the model registry, «کشف مدل‌ها» discovery and the «آزمایش مدل» playground, and
**M4** opens the public gateway (OpenAI-compatible `/v1`) and the «کلیدهای API»
administration that protects it, **M5** adds the routing engine with its dry-run
simulator plus scheduled upstream health checks, **M6** closes the data loop with the
«مصرف» analytics screens, the «گزارش درخواست‌ها» request log and CSV/JSON exports, and
**M7** hardens the result: per-module code splitting, a modal focus contract, demo seed
data, index tuning for the analytics queries and the operations guide.

| Area | State |
| --- | --- |
| API runtime (FastAPI, versioning, structured logging, error envelope) | ✅ implemented |
| PostgreSQL schema + Alembic migration (`0001_initial_schema`) | ✅ implemented |
| Redis foundation (health, rate limiting, graceful degradation) | ✅ implemented |
| Authentication (bootstrap, login, refresh rotation, roles, audit) | ✅ implemented |
| System health, dashboard aggregates, settings, admin users, audit log | ✅ implemented |
| Admin panel shell, i18n (fa default, en secondary), Persian typography, RTL | ✅ implemented |
| Production configuration validation, secret redaction, trusted-proxy handling | ✅ implemented |
| Providers & credentials (CRUD, encrypted secrets, verification, connectivity test) | ✅ implemented |
| Models, discovery and the model playground (M3) | ✅ implemented |
| API keys and the public gateway (M4) | ✅ implemented |
| Routing engine, simulator and health checks (M5) | ✅ implemented |
| Usage analytics, request logs and exports (M6) | ✅ implemented |
| Hardening: lazy routes, focus contract, seeds, indexes, ops docs (M7) | ✅ implemented |

Nothing is **faked**: every module of `PROMPT.md` section 5 now renders a real screen
backed by real rows, and `GET /api/v1/system/roadmap` reports each one with
`state: "implemented"` and the endpoint that serves it. Empty states say what is
missing instead of inventing traffic — the dashboard and the usage screens read the
database, so they show zeros until a provider and a request exist.

---

## Repository layout

```text
backend/                  FastAPI service (English identifiers, English API)
├── app/
│   ├── api/v1/           HTTP layer — thin routes, no business logic
│   ├── auth/             authentication service + RBAC dependencies
│   ├── core/             config, logging, errors, security, crypto
│   ├── database/         async engine, session unit-of-work, Redis client
│   ├── models/           SQLAlchemy models for all planned modules
│   ├── providers/        upstream provider registry + HTTP adapters (M2)
│   ├── health/           readiness probes, typed health targets, failure observations
│   ├── router/           pure routing engine (strategies, scoring, explanations)
│   ├── repositories/     data access
│   ├── schemas/          Pydantic contracts (the frozen API surface)
│   ├── services/         audit, settings, dashboard, gateway, usage, rate limiting
│   └── api/gateway/      OpenAI-compatible public surface (/v1)
├── alembic/              migrations
└── tests/                pytest suite (268 tests)

frontend/                 Persian-first admin panel (React + TypeScript + Vite)
├── src/i18n/             fa.ts (all Persian copy), en.ts, formatters, dynamic keys
├── src/components/       ui primitives, common (Ltr, CodeBlock…), layout shell
├── src/features/         auth, dashboard, providers (+credentials), models, api-keys, routing, health, usage, logs, users, audit, settings
├── src/lib/              API client, query client, locale (Jalali conversion) and theme providers
└── src/test/             i18n parity, RTL guarantees, formatters, smoke tests

scripts/dev_services.py   embedded PostgreSQL + Redis for machines without Docker
backend/app/seeds/        demo dataset (`python -m app.seeds`)
docs/api.md               endpoint reference and error contract
docs/operations.md        configuration, migrations, backups, retention, upgrades
docs/accessibility.md     keyboard, semantics, RTL and 1280/1920px audit
PROMPT.md                 the master build prompt
```

---

## Quick start

### Option A — Docker Compose (reference deployment)

```bash
cp .env.example .env          # then set the four required values
docker compose up --build
```

`docker-compose.yml` refuses to start without them (that is deliberate):

| Variable | Purpose |
| --- | --- |
| `XEREX_SECRET_KEY` | JWT signing key (≥ 32 random characters) |
| `XEREX_CREDENTIALS_ENCRYPTION_KEY` | 32 bytes of url-safe base64 (or 64 hex chars) that encrypt provider credentials |
| `POSTGRES_PASSWORD` / `REDIS_PASSWORD` | database and cache credentials |

* Admin panel → <http://localhost:8080>
* API docs (development only) → <http://localhost:8000/docs>

On first start set `XEREX_BOOTSTRAP_ENABLED=true` for one boot: the panel shows the
Persian **«راه‌اندازی اولیه»** screen, you create the owner account and you are signed
in. Bootstrap is off by default everywhere else — production never silently allows
first-run account creation.

**Local development with containers** (database and cache ports bound to
`127.0.0.1`, development secrets, bootstrap allowed):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yaml up --build
```

### Option B — local development without Docker

The repository ships `scripts/dev_services.py`, which boots a real PostgreSQL and a
real Redis from the `pgserver` / `redislite` wheels — no container runtime needed.

```bash
make install              # Python venv (~/.local/state/xerex-dev/venv) + npm packages
make env                  # creates .env with generated secrets
make services-up          # embedded PostgreSQL + Redis
make migrate              # alembic upgrade head
make api                  # API on http://localhost:8000
make web                  # panel on http://localhost:5173 (proxies /api to the API)
```

`make help` lists every target (tests, lint, build, migrations, service control).

Browser code only ever calls relative URLs (`/api/v1/...`). In development Vite
proxies them to `127.0.0.1:8000`; in production nginx does the same. That keeps
cookies, CORS and preview hosts simple.

---

## Persian / RTL implementation notes

The panel is built for Persian users first; the rules live in `PROMPT.md` §14 and are
enforced by tooling rather than by review alone.

* **Document root** — `<html lang="fa" dir="rtl">` in `index.html`, re-synchronised
  by the i18n layer whenever the language changes.
* **Typography** — self-hosted **Vazirmatn Variable** (`@fontsource-variable/vazirmatn`),
  weights 100–900, `line-height: 1.75` for body text, no letter-spacing, no italics.
* **Localization architecture** — every visible string lives in
  `frontend/src/i18n/fa.ts`; `en.ts` is typed as the same shape, so a missing or
  misspelled key is a **TypeScript error**. Each top-level section is an i18next
  namespace (`dashboard`, `health`, `errors`, …). Adding a language = adding one file.
* **No literal UI text** — `eslint-plugin-i18next` fails the build on a hard-coded
  string in JSX (`npm run lint`).
* **LTR isolation islands** — `<Ltr>` and `<CodeBlock>` apply
  `direction: ltr; unicode-bidi: isolate|isolate-override` so API keys, ids, JSON,
  URLs, model names, IPs and logs stay readable inside Persian sentences and never
  reorder the words around them.
* **Jalali calendar** — dates use `fa-IR-u-ca-persian`
  («۲۷ شهریور ۱۴۰۵»), relative times use `Intl.RelativeTimeFormat('fa-IR')`
  («۳ دقیقه پیش»). Exports and API payloads always use Latin digits and ISO-8601.
* **Numerals** — Persian digits for presentation (configurable), **Latin digits
  always** for technical values.
* **Logical CSS only** — Tailwind logical utilities (`ms-`, `me-`, `ps-`, `pe-`,
  `start-`, `end-`, `text-start`); a test scans the source and fails on `ml-`, `pr-`,
  `left-`, `text-right`, …
* **Status is never colour alone** — every badge pairs colour with Persian text.
* **Directional icons are mirrored, others are not.**
* **Mixed Persian/English** — `Gemini`, `DeepSeek`, `OpenAI`, `Claude`, `Qwen`,
  `Redis`, `PostgreSQL`, `HTTP 429`, `JSON` stay in Latin script inside LTR islands.

### Verification in CI

| Check | Command | What it guarantees |
| --- | --- | --- |
| i18n parity | `npm run test` | `fa` and `en` key sets are identical; Persian is default/fallback |
| Glossary | `npm run test` | Approved terminology (ارائه‌دهنده، مدل‌ها، …) and no Finglish |
| Bidi safety | `npm run test` | Technical values are isolated; API keys survive inside Persian text |
| RTL layout | `npm run test` | No physical direction utilities anywhere in the source |
| Dates/numbers | `npm run test` | Jalali formatting, Persian digits, ISO-8601 for exports |
| No hard-coded copy | `npm run lint` | Every user-visible string comes from the i18n layer |
| Error copy | `npm run test` | API codes render as Persian sentences with the raw code in an LTR badge |
| Smoke test | `npm run test` | Persian sign-in, first-run setup, disabled setup and dashboard render in RTL |
| Production config | `pytest tests/test_config_security.py` | Unsafe secrets/keys/bootstrap settings stop startup |
| Compose posture | `make compose-check` | No public database ports, internal data network, mandatory Redis auth |

---

## API at a glance

All responses are English and machine-readable. Errors use one envelope:

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "Invalid email or password.",
    "request_id": "req_9f2a…"
  }
}
```

The panel maps `error.code` to a Persian message; the raw code stays visible in an
LTR badge next to the message so it can be quoted in a report.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness (no dependency checks) |
| `GET` | `/api/v1/health` | Readiness: database, Redis, runtime |
| `GET` | `/api/v1/health/ready` | Strict readiness (503 when a component is down) |
| `POST` | `/api/v1/auth/bootstrap` | Create the first owner account |
| `GET` | `/api/v1/auth/bootstrap-status` | Whether initial setup is still required |
| `POST` | `/api/v1/auth/login` | Sign in (rate limited per IP + email) |
| `POST` | `/api/v1/auth/refresh` | Rotate the refresh token (single use) |
| `POST` | `/api/v1/auth/logout` | Revoke the current session |
| `GET` | `/api/v1/auth/me` | Read the authenticated administrator |
| `GET` | `/api/v1/system/info` | Version, milestone, locale, capability flags |
| `GET` | `/api/v1/system/roadmap` | Planned modules and their API contracts |
| `GET` | `/api/v1/dashboard/summary` | KPI aggregates, provider health, top models |
| `GET` | `/api/v1/admin-users` · `POST` · `PATCH /{id}` | Administrator management (RBAC) |
| `GET` | `/api/v1/settings` · `PUT /{key}` | Platform settings (locale, numerals, theme, retention) |
| `GET` | `/api/v1/audit-logs` | Administrative audit trail |
| `GET` | `/api/v1/catalog/providers` | Supported provider kinds (metadata only) |
| `GET` | `/api/v1/catalog/routing-strategies` | Routing strategies (metadata only) |
| `GET`·`POST` | `/api/v1/providers` · `GET`·`PATCH`·`DELETE /providers/{provider_id}` | Provider registry (RBAC) |
| `POST` | `/api/v1/providers/{provider_id}/test` | Connectivity test («آزمایش اتصال») |
| `GET`·`POST` | `/api/v1/providers/{provider_id}/credentials` | Credentials — encrypted, masked on read |
| `POST` | `…/credentials/{credential_id}/rotate` · `/verify` | Key rotation and verification |
| `GET`·`POST` | `/api/v1/models` · `GET`·`PATCH`·`DELETE /models/{model_id}` | Model registry |
| `POST` | `/api/v1/models/discover` | «کشف مدل‌ها» — reconcile the provider catalogue |
| `POST` | `/api/v1/models/{model_id}/test` · `/test/stream` | Playground (JSON and SSE) |
| `GET`·`POST` | `/api/v1/models/{model_id}/endpoints` | «نقاط اتصال مدل» with credential binding |
| `POST` | `/api/v1/api-keys` · `POST …/{id}/revoke` | Issue and revoke downstream keys |
| `POST` | `/v1/chat/completions` · `/v1/completions` · `/v1/embeddings` | Public gateway (OpenAI-compatible) |
| `GET` | `/v1/models` · `/v1/info` | Public catalogue and key introspection |
| `POST` | `/api/v1/routing/simulate` | Dry-run the routing decision with reasons |
| `GET`·`POST` | `/api/v1/routing/rules` | Routing rules (strategy, conditions, priority) |
| `GET` | `/api/v1/health/providers` · `/health/observations` | Observed upstream health |
| `POST` | `/api/v1/health/checks` | «اجرای بررسی» — probe the providers now |

Full reference: [`docs/api.md`](./docs/api.md).

**Auth model** — short-lived access JWT (15 min) returned in the body and kept in
memory by the panel; refresh token (14 days) in an `HttpOnly`, `SameSite=Lax` cookie,
rotated on every use and stored hashed. Roles: `owner`, `admin`, `operator`, `viewer`,
enforced server-side.

---

## Architecture notes (pre-M2 correction pass)

The gateway is built in milestones; these structures exist now so later milestones
add behaviour instead of reshaping the schema.

**Endpoint ↔ provider ↔ credential.** A routing decision picks all four
independently: `ModelEndpoint.credential_id` binds an endpoint to a specific
credential, `ModelEndpoint.provider_id` optionally overrides the model's home
provider, and `None` keeps the simple case (the provider's default credential). One
provider can have many credentials, several endpoints can share one credential row
across providers, and secrets are never duplicated:

```text
Model A
  Endpoint 1 → Provider X → Credential 1
  Endpoint 2 → Provider X → Credential 2
  Endpoint 3 → Provider Y → Credential 1
```

`app/services/providers.py` exposes the resolution rule (`pick_credential`, a pure
function, plus `list_routing_targets`) without contacting any upstream provider.

**Health is tracked per dimension.** `health_checks` keeps the portable
`target_type`/`target_id` pointer *and* typed, indexed foreign keys to provider,
credential, model and endpoint, so provider X can be healthy while credential 1 is
`rate_limited`, credential 2 is healthy and one endpoint is degraded. No scheduler
is implemented yet — `app/health/targets.py` is the write path the workers will use.

**One request, many attempts.** `client_requests` holds one row per downstream
request (requested model, attempt count, final outcome, aggregate tokens/cost),
while `usage_records` holds one row per upstream *attempt* (provider, credential,
model, endpoint, tokens, cost, error, retryable) — including several attempts with
the same client request id, which is why that column is no longer unique. Tokens
and cost are therefore attributable per attempt and per request.

**Rate limiting is policy driven.** `RateLimitScope` names the dimension (login
today; api key, administrator, IP, provider, credential, endpoint, model and plan
in M4) and `RateLimitPolicy` carries the numbers, so the login limiter and the
future gateway limiter share the engine but never their configuration or state.
`GatewayRateLimiter` is an honest placeholder that raises `not_implemented`.

## Database

`0001_initial_schema` creates the full schema so later milestones add behaviour, not
tables: `admin_users`, `refresh_tokens`, `providers`, `provider_credentials`, `models`,
`model_endpoints`, `api_keys`, `usage_records`, `usage_daily_rollups`, `routing_rules`,
`health_checks`, `audit_logs`, `settings`.
`0002_routing_targets_usage` adds the pre-M2 structure: endpoint credential/provider
binding, typed health targets and `client_requests` with per-attempt usage columns.
It is additive — existing rows stay valid — and every new column is either nullable
or given a temporary server default that is dropped again in the same migration.

Everything is English, snake_case, UTC, and portable enum values (`openai`, `owner`,
`healthy`). Migrations are reversible:

```bash
cd backend && alembic upgrade head && alembic downgrade base
```

---

## Testing

```bash
make test         # backend (pytest) + frontend (vitest)
make lint         # ruff + eslint (includes the i18n guard)
make typecheck    # tsc --noEmit

# backend only, the way CI runs it (from the backend directory)
cd backend && pytest -q
```

`backend/tests` is a package (`backend/tests/__init__.py`): the test modules import
shared helpers with absolute imports (`from tests.conftest import ...`), which resolve
only while `backend/` is on `sys.path`. That is true for `python -m pytest` but *not*
for the `pytest` console script, which is what CI runs — without the marker, collection
fails with `ModuleNotFoundError: No module named 'tests'`.

* Backend: 138 tests (136 without a PostgreSQL URL; the migration round-trip tests
  skip) — auth flows and bootstrap gating, production configuration
  validation, trusted-proxy address resolution, RBAC/self-escalation, secret
  redaction in logs and audit storage, endpoint↔credential resolution, typed health
  targets, client-request/attempt separation, the rate-limit abstraction, compose
  posture, health probes, security primitives, configuration contract.
* Frontend: 40 tests — i18n parity, glossary, bidi/RTL guarantees, Jalali formatting,
  API client contract, status badges, Persian error copy and an end-to-end render
  smoke test (sign-in, first-run setup, disabled setup, authenticated dashboard).
* CI (`.github/workflows/ci.yml`) runs everything, including the Alembic
  upgrade/downgrade round-trip against PostgreSQL.

---

## Security notes

### Startup configuration validation

`XEREX_ENVIRONMENT=staging|production` makes the API validate its own configuration
while the application is created and **refuse to start** instead of running
insecurely. Blocking conditions:

| Condition | Why |
| --- | --- |
| `XEREX_SECRET_KEY` missing | no silently generated signing key outside development/test |
| `XEREX_SECRET_KEY` short, placeholder (`change-me-in-production`), low entropy | those values end up in repositories |
| `XEREX_CREDENTIALS_ENCRYPTION_KEY` missing | provider secrets must not be protected by a key derived from the JWT secret |
| encryption key malformed (not 32 base64 bytes / 64 hex) | a typo must not silently weaken AES-GCM |
| encryption key equal to the JWT secret | one leaked value would compromise both |
| `XEREX_CORS_ORIGINS` containing `*` | cookies are sent with credentials |
| invalid `XEREX_TRUSTED_PROXIES` entries | a typo must not widen the trust boundary |

Everything else is reported as a startup **warning**: bootstrap explicitly enabled,
Redis without authentication, no trusted proxies configured, `XEREX_DEBUG=true`.

### First-run bootstrap

* Only possible while **zero** administrators exist.
* `XEREX_BOOTSTRAP_ENABLED` decides: explicit `true`/`false` always wins, unset means
  *enabled in development/test, disabled in staging/production*.
* `GET /api/v1/auth/bootstrap-status` returns `bootstrap_allowed`
  (`requires_bootstrap && bootstrap_enabled`) — the value the panel acts on.
* After the first owner exists, bootstrap answers `409 bootstrap_closed`; when the
  switch is off it answers `403 bootstrap_disabled`.

### Provider credential encryption

AES-256-GCM with `XEREX_CREDENTIALS_ENCRYPTION_KEY`. Plaintext is never returned by
the API (the read contract exposes only a masked `key_hint`).

**Rotation is documented but not implemented.** Ciphertexts are self-contained
(`nonce || ciphertext`), so a maintenance task can decrypt existing
`provider_credentials` rows with the old key and re-encrypt them with the new one —
one transaction per row, no other table involved. Until a key-version column exists,
rotation is an offline operation: enter maintenance, re-encrypt, swap the key,
restart. `app/core/crypto.py::key_fingerprint()` is logged at startup (a truncated
hash, never the key) so an operator can confirm which key is active.

### Client address behind proxies

`X-Forwarded-For` is honoured **only** when the direct peer is listed in
`XEREX_TRUSTED_PROXIES`. A direct client cannot spoof its address by sending the
header; behind a reverse proxy the chain is walked right-to-left to the first
untrusted hop. The resolved address is what audit records and the login limiter use.

The trust decision belongs to the application, so uvicorn is started with
`--no-proxy-headers` (Dockerfile, `make dev`) — otherwise uvicorn would replace the
peer address with the header value before the check runs. Verified end to end: with
`XEREX_TRUSTED_PROXIES` empty, `POST /auth/login` carrying
`X-Forwarded-For: 203.0.113.9` is audited as `127.0.0.1`; with `127.0.0.0/8` listed it
is audited as `203.0.113.9`.

In `docker-compose.yml` exactly one peer is trusted: the panel container
(`172.28.0.10`, fixed through the `edge` network's IPAM block), which is the only
process that appends the real client address. Traffic that reaches the published API
port without going through nginx carries the bridge gateway as its peer, so its
`X-Forwarded-For` is ignored. Deploying behind another proxy means adding its address
(or CIDR) to `XEREX_TRUSTED_PROXIES`.

### Other guarantees

* Argon2id password hashing; JWT HS256 with issuer and type validation.
* Refresh tokens are stored hashed, are single-use (rotated on every refresh) and
  live in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` in production).
* Downstream API keys are stored hashed and shown once, with a `xrx_live_…` prefix hint.
* Secrets are never logged: log payloads and audit `diff` mappings pass through a
  recursive redactor (`app/core/redaction.py`).
* RBAC is enforced server-side; an administrator cannot create an owner, promote
  anybody to owner, or change their own role.
* Login is rate limited (Redis); the limiter fails **open** unless
  `XEREX_REDIS_REQUIRED=true`, in which case the request fails with
  `dependency_unavailable` rather than losing protection silently.
* Redis authentication comes from `XEREX_REDIS_PASSWORD` (or credentials inside
  `XEREX_REDIS_URL`); the application injects them into the URL and no password is
  ever committed.
* Every administrative mutation writes an `audit_logs` row with the actor, IP and
  request id.
* `XEREX_ENVIRONMENT=production` disables interactive docs and enables secure
  cookies; run behind TLS.

### Container posture

`docker-compose.yml` (production posture):

* PostgreSQL and Redis publish **no** ports;
* they live on an `internal: true` network with no route to the outside world;
* only the API (`:8000`) and the nginx-served panel (`:8080`) are reachable;
* the API trusts forwarded headers from the panel container only, and never from
  uvicorn itself (`--no-proxy-headers`), so direct API clients cannot spoof their IP;
* Redis requires a password supplied through the environment;
* the API receives the database credentials through the environment, never inside a
  connection-string URL.

The development override (`docker-compose.dev.yaml`) binds the data ports to
`127.0.0.1` only, so a developer keeps `psql`/`redis-cli` access without exposing
anything. `make compose-check` validates these properties without Docker;
`make compose-config` renders the merged files (requires Docker, also run in CI).

---

## Roadmap

| Milestone | Scope |
| --- | --- |
| **M1** ✅ | Foundation: config, database, Redis, auth, health, Persian RTL shell |
| **M2** ✅ | Providers & credentials: CRUD, encrypted secrets, verification, connectivity test |
| **M3** ✅ | Models: discovery, pricing, capabilities, model playground |
| **M4** ✅ | API keys and the OpenAI-compatible public gateway |
| **M5** ✅ | Routing engine, dry-run simulator and scheduled health checks |
| **M6** ✅ | Usage analytics, request logs, exports and daily rollups |
| **M7** ✅ | Hardening: performance, accessibility, RTL audit, documentation, seed data |

---

## Local sandbox account

A development database created by the instructions above contains one owner account so
the panel can be explored immediately:

```text
email:    admin@xerex.ai
password: xerex-dev-admin-2026
```

This exists **only** in local development databases. Delete the database (or change the
password) before deploying anywhere reachable; production deployments always start with
the Persian first-run screen and no accounts.
