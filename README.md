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

## Current status — milestone M1

The full-stack foundation is in place, including authentication, the database
schema for every planned module, and a Persian-first admin shell.

| Area | State |
| --- | --- |
| API runtime (FastAPI, versioning, structured logging, error envelope) | ✅ implemented |
| PostgreSQL schema + Alembic migration (`0001_initial_schema`) | ✅ implemented |
| Redis foundation (health, rate limiting, graceful degradation) | ✅ implemented |
| Authentication (bootstrap, login, refresh rotation, roles, audit) | ✅ implemented |
| System health, dashboard aggregates, settings, admin users, audit log | ✅ implemented |
| Admin panel shell, i18n (fa default, en secondary), Persian typography, RTL | ✅ implemented |
| Providers, credentials, models, API keys, routing, usage, request logs, gateway | ⏳ planned (M2–M6) |

Planned modules are **not faked**: they render an honest placeholder that shows the
milestone and the planned API contract, and the API reports
`state: "planned"` through `GET /api/v1/system/roadmap`. The dashboard reads real
rows from the database, so its numbers are `0` until a provider exists.

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
│   ├── providers/        upstream provider registry (adapters land in M2)
│   ├── repositories/     data access
│   ├── router/           smart routing strategies (engine lands in M5)
│   ├── schemas/          Pydantic contracts (the frozen API surface)
│   ├── services/         audit, settings, dashboard, rate limiting
│   └── health/           readiness probes and runtime state
├── alembic/              migrations
└── tests/                pytest suite (38 tests)

frontend/                 Persian-first admin panel (React + TypeScript + Vite)
├── src/i18n/             fa.ts (all Persian copy), en.ts, formatters, dynamic keys
├── src/components/       ui primitives, common (Ltr, CodeBlock…), layout shell
├── src/features/         auth, dashboard, health, users, audit, settings
├── src/lib/              API client, query client, locale and theme providers
└── src/test/             i18n parity, RTL guarantees, formatters, smoke tests

scripts/dev_services.py   embedded PostgreSQL + Redis for machines without Docker
docs/api.md               endpoint reference and error contract
PROMPT.md                 the master build prompt
```

---

## Quick start

### Option A — Docker Compose (reference deployment)

```bash
cp .env.example .env          # set XEREX_SECRET_KEY and XEREX_CREDENTIALS_ENCRYPTION_KEY
docker compose up --build
```

* Admin panel → <http://localhost:8080>
* API docs (development only) → <http://localhost:8000/docs>

On first start the panel shows the Persian **«راه‌اندازی اولیه»** screen: create the
owner account and you are signed in.

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
| Smoke test | `npm run test` | Persian sign-in, first-run setup and dashboard render in RTL |

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

Full reference: [`docs/api.md`](./docs/api.md).

**Auth model** — short-lived access JWT (15 min) returned in the body and kept in
memory by the panel; refresh token (14 days) in an `HttpOnly`, `SameSite=Lax` cookie,
rotated on every use and stored hashed. Roles: `owner`, `admin`, `operator`, `viewer`,
enforced server-side.

---

## Database

`0001_initial_schema` creates the full schema so later milestones add behaviour, not
tables: `admin_users`, `refresh_tokens`, `providers`, `provider_credentials`, `models`,
`model_endpoints`, `api_keys`, `usage_records`, `usage_daily_rollups`, `routing_rules`,
`health_checks`, `audit_logs`, `settings`.

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
```

* Backend: 38 tests — auth flows, RBAC, settings validation, audit trail, health
  probes, security primitives, configuration contract, dashboard honesty.
* Frontend: 38 tests — i18n parity, glossary, bidi/RTL guarantees, Jalali formatting,
  API client contract, status badges, Persian error copy and an end-to-end render
  smoke test (sign-in, first-run setup, authenticated dashboard).
* CI (`.github/workflows/ci.yml`) runs everything, including the Alembic
  upgrade/downgrade round-trip against PostgreSQL.

---

## Security notes

* Argon2id password hashing; JWT HS256 with issuer and type validation.
* Provider credentials are encrypted with AES-256-GCM
  (`XEREX_CREDENTIALS_ENCRYPTION_KEY`); plaintext is never returned after creation.
* Downstream API keys are stored hashed and shown once, with a `xrx_live_…` prefix hint.
* Login is rate limited (Redis); the limiter fails **open** when Redis is unavailable
  unless `XEREX_REDIS_REQUIRED=true`.
* Every administrative mutation writes an `audit_logs` row with the actor, IP and
  request id.
* Set `XEREX_ENVIRONMENT=production` to disable interactive docs and enable
  secure cookies; run behind TLS.

---

## Roadmap

| Milestone | Scope |
| --- | --- |
| **M1** ✅ | Foundation: config, database, Redis, auth, health, Persian RTL shell |
| **M2** | Providers & credentials: CRUD, encrypted secrets, verification, connectivity test |
| **M3** | Models: discovery, pricing, capabilities, model playground |
| **M4** | Gateway & API keys: OpenAI-compatible endpoints, quota, usage recording |
| **M5** | Health monitoring & smart routing: scheduled checks, strategies, dry-run simulator |
| **M6** | Usage analytics, request logs, exports and retention |
| **M7** | Hardening: performance, accessibility, RTL audit, documentation |

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
