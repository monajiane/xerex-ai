"""Configuration contract and migration round-trip.

The migration check runs only when a PostgreSQL test URL is available
(``XEREX_TEST_DATABASE_URL``); the SQLite fallback in the unit-suite deliberately
skips it because the production schema targets PostgreSQL.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

from app.core.config import Settings

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_settings_defaults_are_persian_first(monkeypatch) -> None:
    for key in list(os.environ):
        if key.startswith("XEREX_"):
            monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.default_locale == "fa"
    assert settings.supported_locales == ["fa", "en"]
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.access_token_ttl_minutes == 15


def test_cors_origins_accept_csv(monkeypatch) -> None:
    monkeypatch.setenv("XEREX_CORS_ORIGINS", "http://a.test,http://b.test")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://a.test", "http://b.test"]


def test_api_prefix_is_normalized(monkeypatch) -> None:
    monkeypatch.setenv("XEREX_API_V1_PREFIX", "api/v2/")
    settings = Settings(_env_file=None)
    assert settings.api_v1_prefix == "/api/v2"


@pytest.mark.skipif(
    not os.environ.get("XEREX_TEST_DATABASE_URL"),
    reason="set XEREX_TEST_DATABASE_URL to a disposable PostgreSQL database to run migrations",
)
def test_migrations_upgrade_and_downgrade() -> None:
    env = {**os.environ, "XEREX_DATABASE_URL": os.environ["XEREX_TEST_DATABASE_URL"]}
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "base"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert downgrade.returncode == 0, downgrade.stderr


@pytest.mark.skipif(
    not os.environ.get("XEREX_TEST_DATABASE_URL"),
    reason="set XEREX_TEST_DATABASE_URL to a disposable PostgreSQL database to run migrations",
)
async def test_migration_produces_the_expected_structure() -> None:
    """Fresh upgrade → verify the foreign keys and indexes the architecture relies on."""
    from sqlalchemy import inspect
    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ["XEREX_TEST_DATABASE_URL"]
    env = {**os.environ, "XEREX_DATABASE_URL": url}
    import asyncio

    def _run_migrations() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    upgrade = await asyncio.to_thread(_run_migrations)
    assert upgrade.returncode == 0, upgrade.stderr

    engine = create_async_engine(url)

    def _inspect(connection):  # noqa: ANN001
        inspector = inspect(connection)
        return {
            "tables": set(inspector.get_table_names()),
            "endpoint_columns": {
                column["name"] for column in inspector.get_columns("model_endpoints")
            },
            "health_columns": {column["name"] for column in inspector.get_columns("health_checks")},
            "usage_columns": {column["name"] for column in inspector.get_columns("usage_records")},
            "usage_indexes": {
                index["name"]: index["unique"] for index in inspector.get_indexes("usage_records")
            },
            "usage_unique": {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("usage_records")
            },
            "usage_foreign_keys": {
                foreign_key["constrained_columns"][0]: (
                    foreign_key["referred_table"],
                    foreign_key.get("options", {}).get("ondelete"),
                )
                for foreign_key in inspector.get_foreign_keys("usage_records")
            },
            "client_request_indexes": {
                index["name"]: index["unique"] for index in inspector.get_indexes("client_requests")
            },
        }

    async with engine.connect() as connection:
        data = await connection.run_sync(_inspect)
    await engine.dispose()

    assert {"client_requests", "usage_records", "health_checks"} <= data["tables"]
    assert {"credential_id", "provider_id"} <= data["endpoint_columns"]
    assert {"provider_id", "credential_id", "model_id", "endpoint_id"} <= data["health_columns"]
    assert {
        "client_request_id",
        "attempt_number",
        "is_final",
        "retryable",
        "credential_id",
        "endpoint_id",
    } <= data["usage_columns"]

    assert data["usage_indexes"]["ix_usage_records_request_id"] is False
    assert data["usage_unique"] >= {"uq_usage_records_attempt_number"}
    assert data["usage_foreign_keys"]["client_request_id"] == ("client_requests", "CASCADE")
    assert data["usage_foreign_keys"]["credential_id"] == ("provider_credentials", "SET NULL")
    assert data["usage_foreign_keys"]["endpoint_id"] == ("model_endpoints", "SET NULL")
    assert data["client_request_indexes"]["ix_client_requests_request_id"] is True
