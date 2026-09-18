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
