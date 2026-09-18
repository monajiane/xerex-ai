# Xerex AI — Master Build Prompt (v2, Persian-first Admin Panel)

> This document is the single source of truth for building **Xerex AI**.
> It is written in English on purpose: the backend, the API, the database and the source code are
> English-first. Only the **user-facing Admin Panel** is Persian-first and RTL.
> Section 14 (**Persian UI / RTL Requirement**) is the authoritative reference for all UI work.

---

## 0. How to use this document

1. Read sections 1–13 for product scope, architecture and engineering rules.
2. Read section 14 **before writing a single line of frontend code**.
3. When a requirement here conflicts with a habit or a template, this document wins.
4. Internal identifiers stay English. Visible strings are Persian and live only in the i18n layer.

---

## 1. Product Overview

Xerex AI is a **self-hosted AI management platform**: a unified LLM gateway plus an
enterprise-grade administration panel.

It lets an operator:

- Connect multiple AI providers (Gemini, DeepSeek, OpenAI, Claude, Qwen and any OpenAI-compatible endpoint).
- Discover and register models from those providers automatically.
- Store and verify provider credentials securely.
- Issue and manage downstream `xrx_live_...` API keys with scopes, quotas and rate limits.
- Continuously monitor provider / model / endpoint health.
- Route incoming requests intelligently (priority, weighted, latency-aware, cost-aware, failover).
- Track token usage, cost, latency and error rate per provider, model and API key.
- Audit every administrative action.

Two distinct surfaces, two distinct languages:

| Surface | Language | Direction |
| --- | --- | --- |
| Public Gateway API (`/v1/...`) | English | n/a |
| Admin API (`/api/v1/admin/...`) | English | n/a |
| **Admin Panel (web UI)** | **Persian (fa)** | **RTL** |
| Secondary UI language (optional) | English (en) | LTR |

---

## 2. Tech Stack (baseline)

**Backend**

- Python 3.12, FastAPI, Pydantic v2
- SQLAlchemy 2.x + Alembic migrations
- PostgreSQL 16 (source of truth), Redis 7 (cache, rate limits, queue backend)
- httpx for upstream provider calls, SSE for streaming
- Arq (or Celery) for background jobs: model discovery, health checks, usage aggregation
- Authentication: short-lived access JWT + rotating refresh token, Argon2id password hashing
- Secrets at rest encrypted with AES-GCM (or Fernet); encryption key from environment
- pytest + httpx test client, factory-based fixtures

**Frontend**

- React 18 + TypeScript + Vite
- Tailwind CSS with logical-property utilities (`ms-*`, `me-*`, `ps-*`, `pe-*`, `start-*`, `end-*`)
- shadcn/ui-style component primitives (owned in-repo, not a black box)
- TanStack Query for server state, React Router for routing
- i18next + react-i18next for localization (see 14.5)
- Recharts (or ECharts) for charts, with explicit RTL handling
- Vazirmatn as the Persian UI font (self-hosted, see 14.3)
- Vitest + React Testing Library, Playwright for E2E

**Infrastructure**

- Docker Compose (api, worker, scheduler, postgres, redis, web)
- `.env.example` with documented variables, Makefile or task runner
- GitHub Actions CI: lint, type-check, unit tests, migration check, build

> Existing identifiers, table names, column names, env vars and API paths are **never** renamed
> to Persian. Persian exists only in the presentation layer.

---

## 3. Domain Model (English identifiers)

All identifiers, tables, columns and JSON fields are English and snake_case.

- `providers` — id, name, kind (`openai` | `anthropic` | `google` | `deepseek` | `qwen` | `openai_compatible`),
  base_url, enabled, priority, weight, timeout_ms, max_retries, created_at, updated_at
- `provider_credentials` — id, provider_id, label, encrypted_secret, key_hint, status,
  last_verified_at, created_at
- `models` — id, provider_id, name, display_name, context_window, max_output_tokens,
  input_price_per_1m, output_price_per_1m, capabilities (jsonb), enabled, deprecated, discovered_at
- `model_endpoints` — id, model_id, path, method, streaming_supported, param_map (jsonb), enabled
- `api_keys` — id, name, prefix, hash, scopes (jsonb), rate_limit_per_min, quota_tokens, expires_at,
  last_used_at, revoked_at, created_by
- `routing_rules` — id, name, strategy, match_conditions (jsonb), target_model_ids (jsonb),
  fallback_chain (jsonb), enabled, priority
- `health_checks` — id, target_type (`provider` | `model` | `endpoint`), target_id, status,
  latency_ms, status_code, error_code, checked_at
- `usage_records` — id, request_id, api_key_id, provider_id, model_id, input_tokens, output_tokens,
  total_tokens, cost, latency_ms, status_code, error_code, created_at
- `usage_daily_rollups` — day, provider_id, model_id, api_key_id, requests, tokens, cost, p95_latency_ms, error_rate
- `admin_users` — id, email, password_hash, role (`owner` | `admin` | `operator` | `viewer`),
  mfa_enabled, status, last_login_at
- `audit_logs` — id, actor_id, action, entity_type, entity_id, diff (jsonb), ip, user_agent, created_at
- `settings` — key, value (jsonb), updated_by, updated_at

Rules:

- `provider_id`, `model_endpoint`, `api_key_id`, `request_id` and every other field name stay English
  in code, in URLs, in JSON responses and in exports — even though the Persian UI labels them
  **«ارائه‌دهنده»**, **«نقطه اتصال مدل»**, **«شناسه کلید API»** and **«شناسه درخواست»**.
- Money is stored as decimal with explicit currency; timestamps are stored as UTC ISO-8601.

---

## 4. Public Gateway API (English)

OpenAI-compatible surface:

- `POST /v1/chat/completions` (streaming and non-streaming)
- `POST /v1/completions`
- `POST /v1/embeddings`
- `GET  /v1/models`

Admin surface (authenticated, still English):

- `/api/v1/admin/providers`, `/credentials`, `/models`, `/model-endpoints`, `/api-keys`,
  `/routing-rules`, `/health`, `/usage`, `/logs`, `/users`, `/settings`, `/audit-logs`

Uniform error envelope (English, machine-readable):

```json
{
  "error": {
    "code": "provider_rate_limited",
    "message": "Upstream provider rate limit exceeded.",
    "request_id": "req_01H...",
    "details": { "retry_after_seconds": 12 }
  }
}
```

**Localization contract:** the backend never returns Persian text. It returns a stable
`error.code`; the Persian Admin Panel maps that code to a Persian message through the i18n layer
(see 14.5). Unknown codes fall back to a generic Persian message plus the raw code in an LTR badge.

---

## 5. Admin Panel Modules

Each module is Persian-labeled in the navigation and fully RTL.
English name → Persian navigation label → scope.

1. **داشبورد** (Dashboard) — KPI cards (requests, tokens, cost, p95 latency, error rate, active providers),
   traffic chart, top models, recent failures, provider health strip, "آخرین بررسی" timestamps.
2. **ارائه‌دهندگان** (Providers) — list, add, edit, enable/disable, kind selector, base URL,
   timeout/retries, priority/weight, link to credentials, "آزمایش اتصال".
3. **اطلاعات احراز هویت** (Credentials) — add, edit, delete, masked display with key hint,
   verify, rotate, per-credential status and last verification time.
4. **مدل‌ها** (Models) — manual add, "کشف مدل‌ها" per provider, capability badges, pricing fields,
   enable/disable, deprecate, "آزمایش مدل" playground (prompt, temperature, streaming output, token count).
5. **کلیدهای API** (API Keys) — create with scopes/quota/expiry, one-time secret reveal with copy button,
   revoke, per-key usage and last-used time.
6. **سلامت سیستم** (Health) — per provider/model/endpoint status, latency sparkline, error breakdown,
   check interval, "بررسی سلامت" now, incident history.
7. **مسیریابی** (Routing) — strategy per rule, priority/weight ordering with drag & drop, fallback chain
   builder, "مسیریابی هوشمند" dry-run simulator.
8. **مصرف** (Usage) — filters (Jalali date range, provider, model, API key), token counters, cost,
   export CSV/JSON (exports always use Latin digits and ISO-8601 timestamps).
9. **گزارش‌ها** (Logs) — request logs with request_id, status, latency, error code, provider/model;
   filters, detail drawer with an LTR JSON viewer and copy-to-clipboard.
10. **کاربران** (Users) — admin users, roles, invite, disable, password reset, active sessions.
11. **تنظیمات** (Settings) — general, security, localization (language, numeral style, calendar),
    notifications, retention policy, integrations.

Every module must implement four states with Persian copy: **loading / empty / error / success**.
Every destructive action requires a Persian confirmation dialog. Every list has a meaningful empty state
(e.g. «هنوز ارائه‌دهنده‌ای اضافه نشده است»).

---

## 6. Routing Engine

- Strategies: `priority`, `weighted`, `round_robin`, `latency_aware`, `cost_aware`, `failover`.
- Rules are evaluated top-down; the first enabled match wins.
- Fallback chain: on timeout, 429, 5xx or provider error, the next candidate is attempted
  (bounded by `max_retries` and a global request deadline).
- Circuit breaker per provider/credential with cooldown and half-open probing.
- Health-aware: a target marked unhealthy is skipped unless it is the only candidate.
- Dry-run simulator returns the resolved decision path (candidate list, scores, chosen target, reason)
  so an administrator can understand routing without reading logs.

---

## 7. Security

- Admin Panel authentication: session cookie (HttpOnly, Secure, SameSite=Lax) or short-lived JWT + refresh.
- RBAC enforced server-side; the UI hides forbidden actions but never relies on hiding.
- Provider secrets encrypted at rest; never returned by the API in plaintext after creation.
- Downstream API keys stored only as hashes; shown once at creation with prefix for identification
  (`xrx_live_8f2a…`).
- Rate limiting and quota enforcement on the gateway.
- Every administrative mutation writes an `audit_logs` row.
- CSRF protection, strict CORS allowlist, security headers, input validation via Pydantic.

---

## 8. Observability

- Structured JSON logs with `request_id` correlation across gateway → router → provider call.
- Metrics: request rate, latency histograms, error rate by code, token throughput, cost per hour.
- Health probes: liveness/readiness endpoints plus scheduled upstream checks.
- Admin-visible diagnostics are rendered in Persian UI, while raw log lines, stack traces and JSON stay English/LTR.

---

## 9. Non-Functional Requirements

- p95 admin API latency < 300 ms for list endpoints with default pagination.
- Streaming responses must not buffer entire completions.
- Pagination, sorting and filtering on every list endpoint (server-side).
- Idempotent background jobs; safe restarts; no in-memory-only state.
- Graceful degradation when Redis is unavailable (bypass cache, keep serving).
- Full keyboard accessibility and visible focus rings in the Admin Panel.
- All UI copy goes through i18n; zero hard-coded user-visible strings.

---

## 10. Engineering Conventions (English-only internals)

The following must remain **English** and must never be Persianized:

- source code identifiers (variables, functions, classes, types)
- database table names, column names, enum values
- API paths, query parameters, JSON field names, headers
- environment variables and configuration keys
- source code comments and docstrings
- log messages, error codes, stack traces
- Git commit messages, branch names, PR titles
- migration names, test names, fixture names

Persian is allowed in exactly two places:

1. `frontend/src/i18n/fa.ts` (and future locale files) — the only home for Persian UI strings.
2. Administrator-facing documentation text rendered inside the dashboard (help panels, tooltips),
   which must also flow through the i18n layer.

Commit style: `feat(admin): add provider health timeline`,
`fix(i18n): isolate API key rendering in RTL layout`.

---

## 11. Testing & QA

- Backend: unit tests for routing, cost computation, quota enforcement, credential encryption;
  integration tests for gateway endpoints with mocked upstreams.
- Frontend: component tests for i18n completeness, RTL layout invariants and LTR isolation of technical values.
- E2E (Playwright): full admin flows in Persian, including RTL assertions
  (`document.documentElement.dir === 'rtl'`) and a bidi-corruption screenshot test.
- A test must fail if a new user-visible string is added outside the i18n layer.
- A test must fail if `fa` and `en` key sets diverge.

---

## 12. Delivery Milestones

1. **M1 — Foundation:** repo layout, Docker Compose, migrations, config, auth skeleton, i18n bootstrap
   with `fa` default and RTL shell (sidebar, header, theme).
2. **M2 — Providers & Credentials:** CRUD, encryption, verification, Persian forms with validation messages.
3. **M3 — Models & Discovery:** discovery job, model registry, playground.
4. **M4 — Gateway & API Keys:** OpenAI-compatible endpoints, key issuance, quota, usage recording.
5. **M5 — Health & Routing:** scheduled checks, routing engine, dry-run simulator UI.
6. **M6 — Usage, Logs, Users, Settings:** analytics, Jalali date filtering, export, RBAC, audit log viewer.
7. **M7 — Hardening:** performance, accessibility, RTL audit, documentation, seed data.

Each milestone ships with Persian UI, not "translation later".

---

## 13. Definition of Done (global)

- Feature works end-to-end in Persian RTL UI for a Persian-speaking administrator with no English needed,
  except for technical values that are intentionally LTR.
- No user-visible string is hard-coded in a component.
- Backend, API and database remain English and unchanged in naming.
- Tests pass; migrations are reversible; docs updated.
- Screenshot check: layout is correct at 1280px and 1920px, in RTL, with long Persian strings and
  long English technical values shown side by side.

---

## 14. Persian UI / RTL Requirement

The entire Xerex AI Admin Panel must be designed primarily for Persian-speaking users.

### 14.1 Language

The default interface language must be:

**Persian (فارسی)**

All visible UI text must be Persian, including:

- navigation
- buttons
- forms
- labels
- tooltips
- notifications
- validation messages
- error messages shown to administrators
- dashboard statistics
- tables
- modal dialogs
- settings
- provider management
- model management
- user management
- API key management
- health monitoring
- routing configuration
- logs
- documentation/help text inside the dashboard

Do **NOT** use Finglish for normal UI text.

Use proper Persian terminology.

Examples:

```text
Dashboard       → داشبورد
Providers       → ارائه‌دهندگان
Models          → مدل‌ها
API Keys        → کلیدهای API
Credentials     → اطلاعات احراز هویت
Health          → سلامت سیستم
Routing         → مسیریابی
Users           → کاربران
Usage           → مصرف
Settings        → تنظیمات
Logs            → گزارش‌ها
Status          → وضعیت
Enabled         → فعال
Disabled        → غیرفعال
```

Explicitly forbidden in visible text: «لطفا دیتای خود را وارد کنید», «مدل رو انتخاب کن»,
or any mix like «وضعیت Provider». Write «وضعیت ارائه‌دهنده».

Technical identifiers keep their English form as *values*, inside an LTR container:
`provider_id`, `model_endpoint`, `api_key_id`, `xrx_live_8f2a…`, `HTTP 429`, `p95`, `JSON`.

### 14.2 RTL

The entire Admin Panel must support:

```text
direction: rtl
```

and should be properly optimized for Persian.

Use:

```html
<html lang="fa" dir="rtl">
```

where appropriate. The `dir` attribute is set on the document root and never toggled per-component
except for deliberate LTR islands (see 14.4).

Rules:

- Tailwind **logical properties only**: `ms-*`/`me-*`, `ps-*`/`pe-*`, `start-*`/`end-*`,
  `text-start`/`text-end`, `border-s`/`border-e`, `rounded-s-*`/`rounded-e-*`.
  Direct `left-*`/`right-*`/`ml-*`/`mr-*`/`pl-*`/`pr-*` usage is a review failure.
- The sidebar sits on the **right**; the content column flows to its left.
- Tables: header order follows reading order; the first column (name/title) starts at the right;
  numeric columns align consistently and stay in Latin digits (see 14.6).
- Forms: labels and helper text are right-aligned with the control; validation icons and messages
  appear on the correct side; required markers lead the label, not trail it.
- Dialogs, drawers, dropdowns, toasts and popovers open from the logical side.
- Directional icons (arrows, chevrons, "next", "back", breadcrumbs) are mirrored
  (`rtl:-scale-x-100` or a mirrored variant), while non-directional icons are never mirrored.
- Charts: axes, legends and tooltips are positioned and ordered for RTL reading; time axes still run
  left → right chronologically, and that decision must be applied consistently everywhere.
- Overflow, truncation with ellipsis, scrollbars and sticky columns must be verified in RTL.
- Keyboard navigation follows visual order; focus order matches the RTL reading order.
- The layout must be correct at 360px, 768px, 1280px and 1920px widths.

Do **NOT** simply mirror the page mechanically. Make the UI feel naturally designed for Persian users.

### 14.3 Persian Typography

Use a high-quality Persian-compatible web font.

Prefer:

- **Vazirmatn**
- IRANSansX if properly licensed
- another open-source Persian font

Prefer **Vazirmatn** if there is no licensing reason to choose another font.

Implementation requirements:

- Self-host Vazirmatn (`@fontsource/vazirmatn` or local `woff2` assets with `font-display: swap`);
  do not depend on a third-party CDN at runtime.
- Weights: 400 (body), 500 (labels), 600 (section titles), 700 (page titles).
- Fallback stack: `Vazirmatn, "IRANSansX", "Segoe UI", Tahoma, system-ui, sans-serif`.
- Font stack for technical content (keys, code, JSON, logs, IDs): a monospace stack
  (`"JetBrains Mono", "Fira Code", ui-monospace, SFMono-Regular, Menlo, monospace`).
- Persian body line-height ≈ 1.75; never below 1.5. Letter-spacing must stay `normal` (Persian must not be tracked).
- Avoid fake bold/italic; Persian UI text is never italic and never uppercase-transformed.
- Numerals: Persian digits (۰۱۲۳۴۵۶۷۸۹) are acceptable in prose; technical values use Latin digits (see 14.4/14.6).

### 14.4 LTR Isolation for Technical Content

Numbers, technical identifiers, URLs, API keys, model names, code and logs should remain readable
using appropriate LTR formatting where necessary.

Example:

```text
API Key:
xrx_live_8f2a...
```

must not become visually corrupted by RTL rendering.

Implement a shared, reusable presentation component — e.g. `<Ltr>` (inline) and `<CodeBlock>` (block) —
that applies:

- `dir="ltr"`
- `unicode-bidi: isolate` (inline) / `unicode-bidi: isolate-override` where a strict LTR block is required
- monospace font for keys, code, JSON, logs and IDs
- `text-align: left` for blocks; inline values stay in the flow of the Persian sentence without
  reordering surrounding text
- copy-to-clipboard affordance where a value is meant to be copied

Apply LTR isolation to:

- API keys
- URLs
- code
- JSON
- model names
- provider names
- IP addresses
- timestamps when necessary
- technical logs

Also applicable to: `request_id`, error codes, base URLs, endpoint paths, HTTP status codes,
token counts in technical views, IDs in tables, versions, e-mail addresses and file paths.

Every inline technical value in a Persian sentence must be wrapped, e.g.:

```tsx
<p>کلید API: <Ltr>{keyPrefix}</Ltr></p>
<p>وضعیت: <Ltr>HTTP 429</Ltr></p>
```

Test rule: if concatenating a technical value between two Persian words changes the visual order of
either word, the isolation is missing.

### 14.5 Localization Architecture

Do **NOT** hard-code Persian strings throughout React components.

Create a localization system.

For example:

```text
frontend/src/i18n/
├── index.ts        # i18next init, language detection, fallback chain ['fa', 'en']
├── fa.ts           # default language
├── en.ts           # secondary language
├── keys.ts         # exported typed key union derived from fa
└── formatters.ts   # Intl wrappers: numbers, dates, relative time, currency
```

Persian is the default language. English is included as a secondary language so the application can
later support international users. The UI must be built so that adding another language requires
only adding one file — no component rewrites.

Rules:

- Use `react-i18next` with namespaces per module (`dashboard`, `providers`, `models`, `keys`,
  `health`, `routing`, `usage`, `logs`, `users`, `settings`, `common`, `errors`).
- Keys are semantic, never sentences: `providers.form.name.label`, `health.status.degraded`.
- Typed keys: `t()` accepts only keys present in `fa`; a missing key is a TypeScript error.
- Interpolation only for values; never build sentences by concatenation (it breaks RTL and plural rules).
- Plurals via i18next plural suffixes; Persian uses `_one`/`_other`.
- Persian digits, dates and relative times come from `formatters.ts`, not from string templates.
- Backend errors are translated by `error.code` → `errors.<code>`; the raw code stays visible in an LTR badge.
- An ESLint guard (e.g. `i18next/no-literal-string`) runs on JSX; CI fails on new literal UI strings.
- No Persian text outside `i18n/fa.ts`. No English text inside JSX.
- RTL/LTR is a layout concern, not a translation concern: both locales render through the same components,
  with `dir` derived from the active locale (`fa` → `rtl`, `en` → `ltr`).

### 14.6 Persian Date / Number Formatting

Where appropriate:

- use Persian-friendly date formatting (Jalali / Solar Hijri calendar)
- support Persian numerals in presentation where useful
- keep technical values such as token counts, API keys and IDs in a readable technical format

Implementation:

- Dates: `Intl.DateTimeFormat('fa-IR-u-ca-persian', { dateStyle: 'medium' })` → «۲۷ شهریور ۱۴۰۵».
- Date pickers in the admin panel are Jalali with a Persian month grid and Persian week labels
  (week starts Saturday «شنبه»).
- Relative time: `Intl.RelativeTimeFormat('fa-IR')` → «۳ دقیقه پیش» for "آخرین بررسی".
- Numbers: `Intl.NumberFormat('fa-IR')` for presentation (dashboards, counters, percentages, cost).
- Latin digits (0-9) are mandatory for: API keys, request IDs, model names/versions, provider names,
  URLs, IP addresses, HTTP codes, and everything inside code/JSON/log blocks.
- A setting allows "Persian numerals" vs "Latin numerals" in presentation; the technical-content rule
  above always wins over the setting.
- Timezone: display the administrator's configured timezone; store and log UTC.
- Currency: format with Persian-friendly grouping and an explicit currency label («تومان» / «دلار»),
  never an ambiguous bare number.
- CSV/JSON exports, API payloads and log lines always use Latin digits and ISO-8601 timestamps.

The administrator should be able to understand all system information without needing English.

### 14.7 Mixed Persian/English Content

The application will frequently display technical English content such as:

```text
Gemini
DeepSeek
OpenAI
Claude
Qwen
HTTP 429
API
JSON
Redis
PostgreSQL
```

Do not translate proper product/model/provider names. Display them naturally inside the Persian RTL
interface.

Rules:

- Wrap English runs inside Persian sentences in an LTR isolation container and add `lang="en"` for
  screen readers and spell-checkers.
- Prefer neutral sentence structures that survive bidi mixing: «کلید API ساخته شد» rather than
  «کلید API شما ساخته شد: xrx_live_…» stacked ambiguously.
- Never place a bare English value at the end of a Persian sentence, at a line break, or adjacent to
  punctuation without isolation.
- Punctuation follows the Persian sentence, not the embedded English token.
- Mixed values are covered by visual regression tests with long English tokens (e.g. 40+ char keys)
  and long Persian words (e.g. «مسیریابی هوشمند چندمرحله‌ای»).

### 14.8 Admin UX

The Persian Admin Panel should feel like a professional enterprise software product, not a translated template.

Use clear Persian labels and terminology.

Examples:

```text
افزودن ارائه‌دهنده
کشف مدل‌ها
آزمایش مدل
بررسی سلامت
مسیریابی هوشمند
کلیدهای API
مصرف توکن
زمان پاسخ
درصد خطا
آخرین بررسی
فعال‌سازی
غیرفعال‌سازی
ذخیره تغییرات
لغو
حذف
ویرایش
جزئیات
```

Standards:

- One concept → one term, everywhere (a shared glossary, enforced in review; see 14.9).
- Buttons use verb-first phrasing consistent across modules; destructive buttons are visually distinct.
- Status badges use color **plus** Persian text — never color alone.
- Tables: sticky headers, RTL-correct column order, sort indicators on the logical side,
  row action menu opening from the correct edge.
- Empty, loading (skeletons) and error states are written in Persian and actionable.
- Toasts are short, Persian, and never contain raw exception text; raw details live behind «جزئیات».
- Forms validate inline with Persian messages; server-side validation errors map to the same field labels.
- Tooltips explain technical concepts in Persian without translating identifiers:
  e.g. hover over `base_url` → «نقطه اتصال پایه ارائه‌دهنده (base_url)» with the identifier inside an LTR span.
- Accessibility: ARIA labels are Persian; screen-reader-only text is Persian;
  `lang` and `dir` attributes are set on mixed-language nodes.

### 14.9 Persian Terminology Glossary (authoritative)

Navigation:

| English | Persian UI label |
| --- | --- |
| Dashboard | داشبورد |
| Providers | ارائه‌دهندگان |
| Credentials | اطلاعات احراز هویت |
| Models | مدل‌ها |
| Model Endpoints | نقاط اتصال مدل |
| API Keys | کلیدهای API |
| Health | سلامت سیستم |
| Routing | مسیریابی |
| Users | کاربران |
| Usage | مصرف |
| Logs | گزارش‌ها |
| Settings | تنظیمات |

Actions:

| English | Persian UI label |
| --- | --- |
| Add provider | افزودن ارائه‌دهنده |
| Discover models | کشف مدل‌ها |
| Test model | آزمایش مدل |
| Check health | بررسی سلامت |
| Smart routing | مسیریابی هوشمند |
| Enable | فعال‌سازی |
| Disable | غیرفعال‌سازی |
| Save changes | ذخیره تغییرات |
| Cancel | لغو |
| Delete | حذف |
| Edit | ویرایش |
| Details | جزئیات |
| Verify | بررسی اعتبار |
| Rotate key | چرخش کلید |
| Revoke | ابطال |
| Copy | رونوشت |
| Refresh | به‌روزرسانی |
| Search | جست‌وجو |
| Filter | فیلتر |
| Export | خروجی |
| Retry | تلاش مجدد |

Domain terms:

| English | Persian UI label |
| --- | --- |
| Provider | ارائه‌دهنده |
| Kind / Type | نوع |
| Base URL | آدرس پایه |
| Credential | اطلاعات احراز هویت |
| Model | مدل |
| Model endpoint | نقطه اتصال مدل |
| Context window | پنجره زمینه |
| Pricing | قیمت‌گذاری |
| Token usage | مصرف توکن |
| Input / Output tokens | توکن ورودی / خروجی |
| Cost | هزینه |
| Latency | زمان پاسخ |
| p95 latency | زمان پاسخ صدک ۹۵ |
| Error rate | درصد خطا |
| Success rate | نرخ موفقیت |
| Last check | آخرین بررسی |
| Status | وضعیت |
| Healthy / Degraded / Down | سالم / کاهش‌یافته / قطع |
| Active / Inactive | فعال / غیرفعال |
| Rate limit | محدودیت نرخ |
| Quota | سهمیه |
| Scope | محدوده دسترسی |
| Fallback chain | زنجیره جایگزین |
| Strategy | راهبرد |
| Priority | اولویت |
| Weight | وزن |
| Dry run | شبیه‌سازی |
| Audit log | گزارش رویداد |
| Retention | مدت نگهداری |
| Role | نقش |
| Request ID | شناسه درخواست |
| Timeout | مهلت زمانی |
| Retry | تلاش مجدد |

Values that are **never** translated (rendered in LTR containers):
`Gemini`, `DeepSeek`, `OpenAI`, `Claude`, `Qwen`, `Redis`, `PostgreSQL`, `HTTP 429`, `JSON`,
`API`, model identifiers, provider slugs, key strings, URLs, IP addresses, environment variable names.

### 14.10 Acceptance Criteria for the Persian UI

A build is not acceptable unless all of these hold:

1. `<html lang="fa" dir="rtl">` is set for the Persian locale, and `dir` follows the active locale.
2. Every visible string comes from the i18n layer; a CI check fails on hard-coded JSX text.
3. `fa` and `en` key sets are identical; `fa` is the fallback default.
4. No English sentence is visible to a Persian administrator anywhere in the panel.
5. API keys, URLs, code, JSON, model names, provider names, IPs, timestamps and log lines render
   LTR-isolated and are not visually corrupted next to Persian text.
6. No `ml-`/`mr-`/`pl-`/`pr-`/`left-`/`right-` utilities remain in the codebase (logical only).
7. Directional icons are mirrored; non-directional icons are not.
8. Dates display in the Jalali calendar; relative times display in Persian.
9. Tables, forms, dialogs and toasts are RTL-correct at 360px / 768px / 1280px / 1920px.
10. Vazirmatn is the default font, self-hosted, and Persian text has comfortable line-height.
11. Persian terminology matches the glossary in 14.9 with no synonyms drifting between modules.
12. Adding a new language requires adding one file and no component changes.

### 14.11 Important

The backend code, database identifiers, API field names, environment variables, source code comments
and Git commits should remain in English.

Only the user-facing application should be Persian-first.

In other words: `provider_id` and `model_endpoint` stay as they are in the database and in the API,
while the administrator sees **«ارائه‌دهنده»** and **«نقطه اتصال مدل»** in the panel.

The final result should be a **fully Persian, RTL, professional AI management platform**.

---

## 15. Final Note

This project does not ship a translation bolted onto an English product.
It ships a Persian-first, RTL-native admin experience on top of an English-native, standards-compliant
backend and API. Both halves are non-negotiable.
