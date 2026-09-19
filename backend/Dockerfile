# Xerex AI — API image
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System dependencies kept minimal: asyncpg and cryptography ship wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Migrations run before the API starts so a fresh deployment is ready on boot.
# --no-proxy-headers is deliberate: uvicorn must hand the *TCP peer address* to the
# application unchanged. Trusting X-Forwarded-For is a policy decision that belongs to
# the app (XEREX_TRUSTED_PROXIES), otherwise a direct client could spoof its address.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers"]
