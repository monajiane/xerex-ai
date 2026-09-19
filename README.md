# Xerex AI

[![License](https://img.shields.io/badge/license-Proprietary-blue)]()
[![Milestone](https://img.shields.io/badge/milestone-M7-green)]()
[![Backend](https://img.shields.io/badge/backend-FastAPI-blue)]()
[![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20TypeScript%20%2B%20Vite-purple)]()
[![Database](https://img.shields.io/badge/database-PostgreSQL%20%2B%20Redis-blue)]()
[![Language](https://img.shields.io/badge/language-English%2FPersian-informational)]()

Self-hosted AI management platform: a unified LLM gateway plus an enterprise-grade
administration panel. **Persian-first, RTL-native** admin panel with full English API.

---

## ✨ Features

- **Unified LLM Gateway** — OpenAI-compatible `/v1` endpoint for all providers
- **Provider Management** — Register, verify, and manage any LLM provider with encrypted credentials
- **Model Discovery & Playground** — Auto-discover models from providers, test with JSON/SSE streaming
- **Smart Routing Engine** — Weighted routing, dry-run simulator, per-model endpoints
- **API Key Management** — Issue, revoke, and rate-limit downstream API keys
- **Usage Analytics** — Real-time dashboards, request logs, CSV/JSON exports
- **Health Monitoring** — Per-dimension health checks with scheduled probes
- **RBAC Admin Panel** — Persian RTL panel with `owner`, `admin`, `operator`, `viewer` roles
- **Audit Trail** — Every administrative mutation logged with actor, IP, and request ID
- **First-Run Bootstrap** — Secure one-time owner account creation
- **Production-Ready Security** — Config validation, secret redaction, trusted-proxy handling

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [API Reference](#api-reference)
- [Persian / RTL Implementation](#persian--rtl-implementation)
- [Database](#database)
- [Testing](#testing)
- [Security](#security)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Version |
| --- | --- |
| Python | 3.11+ |
| Node.js | 18+ |
| PostgreSQL | 14+ |
| Redis | 7+ |
| Docker & Compose | *(optional — for container deployment)* |

---

### Option A — Docker Compose ⭐ (recommended)

```bash
git clone https://github.com/monajiane/xerex-ai.git
cd xerex-ai
cp .env.example .env
# Edit .env — set the four required values below
docker compose up --build -d
```

**Required environment variables:**

| Variable | Purpose | Example |
| --- | --- | --- |
| `XEREX_SECRET_KEY` | JWT signing key (≥ 32 chars) | `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `XEREX_CREDENTIALS_ENCRYPTION_KEY` | AES-256 key (32 bytes base64) | `python3 -c "import base64,os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"` |
| `POSTGRES_PASSWORD` | Database password | *(any strong password)* |
| `REDIS_PASSWORD` | Redis password | *(any strong password)* |

| URL | Description |
| --- | --- |
| http://localhost:8080 | Admin panel |
| http://localhost:8000/docs | API documentation |
| http://localhost:8000/health | Health check |

**First run:** Set `XEREX_BOOTSTRAP_ENABLED=true` to enable the Persian first-run setup screen.
After creating the owner account, set it to `false`.

**Development with containers** (ports bound to `127.0.0.1` only):
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yaml up --build -d
```

---

### Option B — Local development (no Docker)

```bash
# Create virtual environment and install Python dependencies
python3 -m venv ~/.local/state/xerex-dev/venv
source ~/.local/state/xerex-dev/venv/bin/activate
pip install -e "backend[dev]"

# Install frontend dependencies
cd frontend && npm install && cd ..

# Start embedded PostgreSQL + Redis
python scripts/dev_services.py start

# Generate .env with secrets
python -c "import secrets,base64,os; f=open('.env','w'); f.write(f'XEREX_SECRET_KEY={secrets.token_urlsafe(48)}\nXEREX_CREDENTIALS_ENCRYPTION_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}\nXEREX_BOOTSTRAP_ENABLED=true\nXEREX_ENVIRONMENT=development\n')"

# Set the database URL to use the embedded services
echo 'XEREX_DATABASE_URL=postgresql+asyncpg://postgres@/xerex?host='$(python -c "import os;print(os.path.expanduser('~/.local/state/xerex-dev/pgdata'))") >> .env
echo 'XEREX_REDIS_URL=redis://127.0.0.1:56379/0' >> .env

# Run database migrations
cd backend && python -m alembic upgrade head

# Run the API server
make api    # → http://localhost:8000

# In another terminal, run the frontend
cd frontend && npm run dev    # → http://localhost:5173
```

> **Note:** `scripts/dev_services.py` uses `pgserver` and `redislite` wheels. These require
> Linux. On Windows or when they fail, use SQLite instead by setting:
> ```env
> XEREX_DATABASE_URL=sqlite+aiosqlite:///./xerex.db
> XEREX_REDIS_REQUIRED=false
> ```

---

### Option C — Manual installation

```bash
# 1. Install PostgreSQL & Redis
sudo apt install -y postgresql redis-server
sudo systemctl enable --now postgresql redis-server

# 2. Create database
sudo -u postgres psql -c "CREATE DATABASE xerex;"
sudo -u postgres psql -c "CREATE USER xerex WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE xerex TO xerex;"

# 3. Install Python dependencies
python3 -m venv venv
source venv/bin/activate
pip install -e "backend[dev]"

# 4. Install Node.js dependencies
cd frontend && npm install && cd ..

# 5. Configure .env
cp .env.example .env
nano .env

# 6. Run migrations
cd backend && python -m alembic upgrade head

# 7. Start services
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --no-proxy-headers
cd frontend && npm run dev
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Client Browser                      │
│              (React + TypeScript + Vite)                 │
│                  http://localhost:5173                   │
│                    Persian RTL Panel                     │
└──────────────────────┬──────────────────────────────────┘
                       │ /api/v1/...
                       ▼
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Backend                          │
│                    http://localhost:8000                  │
│                                                          │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌───────────┐  │
│  │  Auth     │ │ Providers │ │  Models   │ │  API Keys │  │
│  │  Bootstrap │ │  Registry │ │  Catalog  │ │  Gateway  │  │
│  └──────────┘ └───────────┘ └──────────┘ └───────────┘  │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌───────────┐  │
│  │  Routing  │ │ Usage     │ │  Health   │ │  Settings │  │
│  │  Engine   │ │ Analytics │ │  Checks   │ │  Admin    │  │
│  └──────────┘ └───────────┘ └──────────┘ └───────────┘  │
│                                                          │
│  ┌───────────────────────────────────────────────────┐   │
│  │  Database (PostgreSQL) │ Cache (Redis)              │   │
│  │  Alembic Migrations  │ Rate Limiting               │   │
│  └───────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

### Repository layout

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

## 📡 API Reference

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

### Core Endpoints

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
| `GET` | `/api/v1/settings` · `PUT /{key}` | Platform settings |
| `GET` | `/api/v1/audit-logs` | Administrative audit trail |

### Providers & Credentials (M2)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`·`POST` | `/api/v1/providers` · `GET`·`PATCH`·`DELETE /providers/{provider_id}` | Provider registry |
| `POST` | `/api/v1/providers/{provider_id}/test` | Connectivity test |
| `GET`·`POST` | `/api/v1/providers/{provider_id}/credentials` | Credentials — encrypted, masked on read |
| `POST` | `…/credentials/{credential_id}/rotate` · `/verify` | Key rotation and verification |
| `GET` | `/api/v1/catalog/providers` | Supported provider kinds (metadata) |

### Models (M3)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET`·`POST` | `/api/v1/models` · `GET`·`PATCH`·`DELETE /models/{model_id}` | Model registry |
| `POST` | `/api/v1/models/discover` | Model discovery |
| `POST` | `/api/v1/models/{model_id}/test` · `/test/stream` | Playground (JSON and SSE) |
| `GET`·`POST` | `/api/v1/models/{model_id}/endpoints` | Endpoints with credential binding |
| `GET` | `/api/v1/catalog/routing-strategies` | Routing strategies (metadata) |

### API Keys & Gateway (M4)

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/api-keys` · `POST …/{id}/revoke` | Issue and revoke downstream keys |
| `POST` | `/v1/chat/completions` · `/v1/completions` · `/v1/embeddings` | Public gateway (OpenAI-compatible) |
| `GET` | `/v1/models` · `/v1/info` | Public catalogue and key introspection |

### Routing (M5)

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/routing/simulate` | Dry-run routing decision with reasons |
| `GET`·`POST` | `/api/v1/routing/rules` | Routing rules (strategy, conditions, priority) |
| `POST` | `/api/v1/health/checks` | Probe all providers now |
| `GET` | `/api/v1/health/providers` · `/health/observations` | Observed upstream health |

### Usage & Analytics (M6)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/usage` | Usage analytics screen |
| `GET` | `/api/v1/logs` | Request logs |
| — | Export | CSV/JSON exports |

---

## 🌐 Persian / RTL Implementation

The admin panel is **Persian-first and RTL-native**. Rules are enforced by tooling.

### Typography
- **Vazirmatn Variable** (`@fontsource-variable/vazirmatn`) — weights 100–900
- `line-height: 1.75` for body text, no letter-spacing, no italics

### Localization Architecture
- Every visible string lives in `frontend/src/i18n/fa.ts`
- `en.ts` is typed as the same shape — missing key = **TypeScript error**
- Each section is an i18next namespace (`dashboard`, `health`, `errors`, …)
- Adding a language = adding one file

### Rules
- **No literal UI text** — `eslint-plugin-i18next` fails build on hard-coded strings
- **LTR isolation islands** — `<Ltr>` and `<CodeBlock>` keep API keys, IDs, JSON readable inside Persian text
- **Jalali calendar** — `fa-IR-u-ca-persian` («۲۷ شهریور ۱۴۰۵»), relative times (`Intl.RelativeTimeFormat`)
- **Logical CSS only** — Tailwind logical utilities (`ms-`, `me-`, `ps-`, `pe-`, `start-`, `end-`, `text-start`)
- **Status never colour alone** — every badge pairs colour with Persian text
- **Technical values always Latin digits** (`API 429`, `JSON`, `HTTP 500`)

### Verification in CI

| Check | Command | Guarantees |
| --- | --- | --- |
| i18n parity | `npm run test` | `fa` and `en` keys identical; Persian is default/fallback |
| Glossary | `npm run test` | Approved terminology, no Finglish |
| Bidi safety | `npm run test` | Technical values isolated inside Persian text |
| RTL layout | `npm run test` | No physical direction utilities in source |
| Dates/numbers | `npm run test` | Jalali formatting, Persian digits, ISO-8601 exports |
| No hard-coded copy | `npm run lint` | Every user-visible string from i18n layer |
| Error copy | `npm run test` | API codes as Persian sentences with raw code in LTR badge |
| Smoke test | `npm run test` | Sign-in, first-run setup, dashboard render in RTL |
| Production config | `pytest tests/test_config_security.py` | Unsafe secrets/keys/bootstrap stop startup |
| Compose posture | `make compose-check` | No public DB ports, internal network, mandatory Redis auth |

---

## 🗄️ Database

`0001_initial_schema` creates the full schema: `admin_users`, `refresh_tokens`, `providers`,
`provider_credentials`, `models`, `model_endpoints`, `api_keys`, `usage_records`,
`usage_daily_rollups`, `routing_rules`, `health_checks`, `audit_logs`, `settings`.

`0002_routing_targets_usage` adds pre-M2 structure with typed health targets and
per-attempt usage columns.

```bash
# Apply migrations
cd backend && alembic upgrade head

# Rollback
cd backend && alembic downgrade base
```

Everything is English, snake_case, UTC, and portable enum values (`openai`, `owner`, `healthy`).

---

## 🧪 Testing

```bash
make test          # backend (pytest) + frontend (vitest)
make lint          # ruff + eslint (includes the i18n guard)
make typecheck     # tsc --noEmit
make format        # ruff format

# Backend only
cd backend && pytest -q

# Frontend only
cd frontend && npm run test
```

**Backend:** 138 tests — auth flows, bootstrap gating, config validation, trusted-proxy
resolution, RBAC, secret redaction, endpoint↔credential resolution, health probes,
security primitives, compose posture.

**Frontend:** 40 tests — i18n parity, glossary, bidi/RTL guarantees, Jalali formatting,
API client contract, status badges, Persian error copy, end-to-end render smoke test.

---

## 🔒 Security

### Startup Validation (`XEREX_ENVIRONMENT=staging|production`)

| Blocking Condition | Why |
| --- | --- |
| `XEREX_SECRET_KEY` missing | No silently generated signing key in production |
| `XEREX_SECRET_KEY` short/placeholder/low entropy | Would end up in repositories |
| `XEREX_CREDENTIALS_ENCRYPTION_KEY` missing | Provider secrets need dedicated encryption |
| Encryption key malformed | Typo must not silently weaken AES-GCM |
| Encryption key = JWT secret | One leak compromises both |
| `XEREX_CORS_ORIGINS` contains `*` | Cookies sent with credentials |
| Invalid `XEREX_TRUSTED_PROXIES` | Typo widens trust boundary |

### Key Guarantees

- **Argon2id** password hashing; **JWT HS256** with issuer and type validation
- **Refresh tokens**: hashed, single-use (rotated on every refresh), `HttpOnly` + `SameSite=Lax` cookie
- **Downstream API keys**: stored hashed, shown once with `xrx_live_…` prefix hint
- **Secrets**: never logged — recursive redactor (`app/core/redaction.py`)
- **RBAC**: server-side enforced; cannot create owner, promote to owner, or change own role
- **Rate limiting**: Redis-based; fails **open** unless `XEREX_REDIS_REQUIRED=true`
- **Audit trail**: every mutation logged with actor, IP, and request ID
- **Proxy handling**: `X-Forwarded-For` honored only for trusted peers; uvicorn runs with `--no-proxy-headers`

---

## 📈 Roadmap

| Milestone | Scope | Status |
| --- | --- | --- |
| **M1** | Foundation: config, database, Redis, auth, health, Persian RTL shell | ✅ |
| **M2** | Providers & credentials: CRUD, encrypted secrets, verification, connectivity test | ✅ |
| **M3** | Models: discovery, pricing, capabilities, model playground | ✅ |
| **M4** | API keys and the OpenAI-compatible public gateway | ✅ |
| **M5** | Routing engine, dry-run simulator, scheduled health checks | ✅ |
| **M6** | Usage analytics, request logs, exports and daily rollups | ✅ |
| **M7** | Hardening: code splitting, modal focus, seed data, index tuning, ops docs | ✅ |

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

### Development workflow

```bash
# Backend
cd backend
source venv/bin/activate
pip install -e "backend[dev]"
python -m alembic upgrade head
python -m pytest -q

# Frontend
cd frontend
npm install
npm run dev
npm run test
npm run lint
npm run typecheck
```

---

## 📄 License

This project is proprietary. See the [LICENSE](LICENSE) file for details.

---

## 📬 Support

- **Documentation:** `docs/api.md`, `docs/operations.md`, `docs/accessibility.md`
- **Full spec:** `PROMPT.md` (master build prompt)
- **Issues:** [GitHub Issues](https://github.com/monajiane/xerex-ai/issues)
- **Email:** admin@xerex.ai

---

## 🏪 Local Sandbox Account

A development database contains one owner account for immediate exploration:

```text
email:    admin@xerex.ai
password: xerex-dev-admin-2026
```

> ⚠️ **This exists only in local development databases.** Delete the database (or change
> the password) before deploying anywhere reachable. Production deployments always start
> with the Persian first-run screen and no accounts.
