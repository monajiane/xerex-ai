# Operations guide

Everything an operator needs after `docker compose up`: how the schema moves, how to fill
a database with demo data, what to back up, and which switches change behaviour at
runtime. The admin panel is Persian-first; this document stays English because it is read
next to shell commands, logs and environment variables.

---

## 1. Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `XEREX_ENVIRONMENT` | `development` | `development` \| `test` \| `staging` \| `production` |
| `XEREX_SECRET_KEY` | — | JWT signing key. Required outside development. |
| `XEREX_CREDENTIALS_ENCRYPTION_KEY` | — | AES-256-GCM key for provider secrets. Required outside development, must differ from the signing key. |
| `XEREX_DATABASE_URL` | `postgresql+asyncpg://…` | Async SQLAlchemy URL. |
| `XEREX_REDIS_URL` | `redis://…` | Rate limiting and cache. The API degrades gracefully when Redis is down. |
| `XEREX_BOOTSTRAP_ENABLED` | env-derived | First-run owner creation. Disabled outside development/test unless set explicitly. |
| `XEREX_HEALTH_SCHEDULER_ENABLED` | `false` | Run upstream health checks on a timer. |
| `XEREX_HEALTH_CHECK_INTERVAL_SECONDS` | `300` | Interval for the scheduler. |
| `XEREX_TRUSTED_PROXY_IPS` | empty | Only these proxies may set client IP headers; forwarding is ignored otherwise. |

`GET /api/v1/system/info` reports the effective environment, milestone and locale, and
`/api/v1/health` reports dependency status, so a deployment can be verified without
reading logs.

### Key rotation

* `XEREX_SECRET_KEY` — rotating it invalidates refresh tokens (administrators sign in
  again); access tokens expire within their short lifetime.
* `XEREX_CREDENTIALS_ENCRYPTION_KEY` — rotating it requires re-entering provider
  credentials, because stored secrets are encrypted with it. There is no re-encryption
  path on purpose: a silent failure mode here would lock every provider out.

---

## 2. Schema and migrations

```bash
cd backend
alembic upgrade head          # apply
alembic downgrade -1          # step back one revision
alembic current               # what is applied
alembic history --verbose     # full chain with descriptions
```

The chain is `0001_initial_schema → 0002_routing_targets_usage → 0003_performance_indexes`.
Every revision is reversible; `0003` only creates indexes and restores the previous
definitions on `downgrade`. `alembic check` must report *no new upgrade operations*
against the models — CI runs it, so a model change without a migration fails the build.

---

## 3. Demo data

The panel is only useful with rows behind it. `app.seeds` writes a complete, obviously
artificial dataset:

```bash
cd backend
python -m app.seeds                     # 7 days of traffic, 24 requests per day
python -m app.seeds --days 30 --per-day 60
python -m app.seeds --no-traffic        # providers/models/keys only
python -m app.seeds --reset             # remove everything the seed created
```

What it writes:

| Entity | Count | Marker |
| --- | --- | --- |
| Provider | 2 | name ends with `(demo)`, slug ends with `-demo` |
| Credential | 2 | placeholder secret `sk-demo-…` |
| Model / endpoint | 3 / 3 | model `gpt-4o-mini-demo` on the backup provider |
| Routing rule | 1 | name ends with `(demo)` |
| API key | 1 | prefix `xrx_live_demo…` (secret printed once) |
| Usage | `days × per-day` requests | request ids start with `req-demo-` |
| Owner account | 1 | `demo@xerex.ai` / `xerex-demo-owner-2026` |

Guarantees:

* **Opt-in** — nothing is seeded automatically, and a `production` environment refuses
  unless `--allow-production` is passed.
* **Idempotent** — running it twice updates nothing and does not duplicate rows; the
  usage rows are generated from a fixed seed, so two fresh runs produce the same picture.
* **Removable** — `--reset` deletes only rows carrying the demo markers. A real provider,
  its credentials and its traffic are left untouched (covered by tests).

---

## 4. Backups

The database is the only stateful component; Redis holds rate-limit counters and cache
entries that can be lost without data loss.

```bash
# logical backup
docker compose exec -T postgres pg_dump -U xerex xerex | gzip > xerex-$(date +%F).sql.gz

# restore into a fresh database
gunzip -c xerex-2026-09-19.sql.gz | docker compose exec -T postgres psql -U xerex -d xerex
```

Notes for a restore:

1. Restore the database, then run `alembic upgrade head` — do not restore into a database
   whose `alembic_version` is ahead of the code.
2. `XEREX_CREDENTIALS_ENCRYPTION_KEY` must be the same key that was active when the backup
   was taken, otherwise stored provider secrets cannot be decrypted (the API reports
   `credential_decryption_failed` and the provider must be re-entered).
3. Audit rows (`audit_logs`) are append-only from the application's point of view and are
   part of the backup; the panel exposes them read-only.

### Retention

`retention.usage_days` and `retention.logs_days` in the settings screen describe the
intended retention window. Nothing is deleted automatically: an operator decides, because
usage rows are the billing and accountability record. The safe procedure is to export
first, then delete:

```bash
# 1. export the window you are about to prune (CSV, one row per attempt)
curl -H "Authorization: Bearer $TOKEN" \
  "https://panel.example.com/api/v1/usage/export?format=csv&date_from=2026-01-01&date_to=2026-01-31" \
  -o usage-2026-01.csv

# 2. then delete rows from usage_records/client_requests for that window
```

`POST /api/v1/usage/rollups/rebuild?day=YYYY-MM-DD` recomputes a day of aggregates from
the stored attempts, so a partial prune can be reflected in the dashboards afterwards.

---

## 5. Health and monitoring

| Signal | Where | Meaning |
| --- | --- | --- |
| `GET /api/v1/health` | unauthenticated | Component readiness (database, Redis, scheduler). |
| `GET /api/v1/health/providers` | panel session | Upstream status per provider/credential with 24h aggregates. |
| `GET /api/v1/system/roadmap` | panel session | Which modules are implemented, and their endpoints. |
| `audit_logs` | panel session | Security and configuration trail (never stores secrets). |

Upstream checks are **on demand** unless `XEREX_HEALTH_SCHEDULER_ENABLED=true`. The
scheduled run uses the same service as the «اجرای بررسی» button, so manual and automatic
results are directly comparable. A provider with no credential is reported as
`credential_missing`, not as an upstream failure.

---

## 6. Rate limiting

* Admin endpoints use an in-process limiter; the gateway limiter is shared through Redis
  when Redis is reachable and degrades to per-process counting when it is not (logged as
  `rate_limit_backend_unavailable`).
* A downstream key's limit is its own `rate_limit_per_min`, otherwise
  `gateway_default_rate_limit_per_min` from the settings screen.
* Exceeding it returns HTTP 429 with the standard error envelope and, for gateway calls,
  triggers failover to the next candidate rather than failing the caller.

---

## 7. Upgrades

```bash
git pull
docker compose build
docker compose run --rm api alembic upgrade head   # migrate before serving
docker compose up -d
curl -fsS https://panel.example.com/api/v1/health  # verify
```

The panel is a static bundle; a new version is picked up on reload. Because pages are
lazy-loaded per module, a browser that keeps an old tab open may request a chunk that no
longer exists after a deploy — the error boundary shows the Persian failure state with a
reload action instead of a blank screen.
