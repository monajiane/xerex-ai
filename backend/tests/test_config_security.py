"""Production configuration safety (correction pass items 1–3 and 5).

The contract these tests lock in:

* development/test keep generated defaults so a fresh checkout boots;
* staging/production refuse to start with a missing, placeholder or low-entropy
  ``XEREX_SECRET_KEY``, with no dedicated ``XEREX_CREDENTIALS_ENCRYPTION_KEY``, or
  with a malformed encryption key;
* the provider-credential key is never silently derived from the JWT secret outside
  development/test;
* Redis credentials can come from the environment and are injected into the
  connection URL instead of being hard-coded.
"""

from __future__ import annotations

import base64
import os

import pytest

from app.core.config import (
    ConfigurationError,
    Settings,
    looks_like_placeholder,
    parse_encryption_key,
)

# 48 url-safe characters, no placeholder markers, high entropy.
VALID_SECRET = "n7Qv2Lx9pR4tYb8Kd3Ws6Jm1Zc5Hg0UaEfTnIoPqBrSvWxyCz"
KEY_BYTES = bytes(range(32))
VALID_KEY_B64 = base64.urlsafe_b64encode(KEY_BYTES).decode("ascii")
VALID_KEY_HEX = KEY_BYTES.hex()


def _production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "production",
        "secret_key": VALID_SECRET,
        "credentials_encryption_key": VALID_KEY_B64,
        "debug": False,
        "bootstrap_enabled": None,
        "redis_password": "a-redis-password",
        "trusted_proxies": ["10.0.0.0/8"],
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Development keeps working out of the box
# --------------------------------------------------------------------------- #
def test_development_generates_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("XEREX_"):
            monkeypatch.delenv(key, raising=False)

    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.secret_key is None
    assert settings.effective_secret_key  # generated
    assert settings.bootstrap_enabled_effective is True
    assert settings.encryption_key_is_derived is True
    assert settings.validate_runtime_security() == []


def test_test_environment_matches_development_defaults() -> None:
    settings = Settings(_env_file=None, environment="test")
    assert settings.bootstrap_enabled_effective is True
    assert settings.validate_runtime_security() == []


# --------------------------------------------------------------------------- #
# Item 2 — production secret validation
# --------------------------------------------------------------------------- #
def test_production_requires_an_explicit_secret_key() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(secret_key=None)
    assert "XEREX_SECRET_KEY" in error.value.problems
    assert "explicitly" in error.value.problems["XEREX_SECRET_KEY"]


def test_production_rejects_placeholder_secret_key() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(secret_key="change-me-in-production-please-rotate-me")
    assert "placeholder" in error.value.problems["XEREX_SECRET_KEY"]


def test_production_rejects_short_secret_key() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(secret_key="short-secret")
    assert "at least 32 characters" in error.value.problems["XEREX_SECRET_KEY"]


def test_production_rejects_low_entropy_secret_key() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(secret_key="a" * 64)
    assert "XEREX_SECRET_KEY" in error.value.problems


def test_no_random_secret_is_generated_in_production() -> None:
    with pytest.raises(ConfigurationError):
        _production(secret_key=None)


def test_staging_is_treated_like_production() -> None:
    with pytest.raises(ConfigurationError):
        Settings(_env_file=None, environment="staging")


def test_secret_key_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("XEREX_"):
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("XEREX_ENVIRONMENT", "production")
    monkeypatch.setenv("XEREX_CREDENTIALS_ENCRYPTION_KEY", VALID_KEY_B64)
    monkeypatch.setenv("XEREX_REDIS_PASSWORD", "from-env")
    monkeypatch.setenv("XEREX_TRUSTED_PROXIES", "10.0.0.0/8")

    with pytest.raises(ConfigurationError) as error:
        Settings(_env_file=None)
    assert "XEREX_SECRET_KEY" in error.value.problems

    monkeypatch.setenv("XEREX_SECRET_KEY", VALID_SECRET)
    settings = Settings(_env_file=None)
    assert settings.effective_secret_key == VALID_SECRET


# --------------------------------------------------------------------------- #
# Item 3 — credential encryption key
# --------------------------------------------------------------------------- #
def test_production_requires_a_dedicated_encryption_key() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(credentials_encryption_key=None)
    assert "XEREX_CREDENTIALS_ENCRYPTION_KEY" in error.value.problems
    assert "explicitly" in error.value.problems["XEREX_CREDENTIALS_ENCRYPTION_KEY"]


def test_production_rejects_malformed_encryption_key() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(credentials_encryption_key="not-really-a-key")
    assert "32 bytes" in error.value.problems["XEREX_CREDENTIALS_ENCRYPTION_KEY"]


def test_production_rejects_the_jwt_secret_as_encryption_key() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(secret_key=VALID_KEY_B64, credentials_encryption_key=VALID_KEY_B64)
    assert (
        "different from XEREX_SECRET_KEY"
        in error.value.problems["XEREX_CREDENTIALS_ENCRYPTION_KEY"]
    )


def test_production_never_derives_the_key_from_the_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _production()
    assert settings.encryption_key_is_derived is False
    assert settings.fernet_key_material == KEY_BYTES

    # Defence in depth: even if the key disappeared after startup validation, the
    # property refuses to fall back to a derived key in a deployed environment.
    monkeypatch.setattr(settings, "credentials_encryption_key", None)
    with pytest.raises(ConfigurationError):
        _ = settings.fernet_key_material


def test_hex_encryption_key_is_accepted() -> None:
    settings = _production(credentials_encryption_key=VALID_KEY_HEX)
    assert settings.fernet_key_material == KEY_BYTES


def test_development_fallback_is_explicit_and_not_a_hash_of_a_bad_key() -> None:
    settings = Settings(
        _env_file=None,
        environment="development",
        credentials_encryption_key="definitely-not-a-key",
    )
    assert settings.encryption_key_is_derived is True
    import hashlib

    assert (
        settings.fernet_key_material != hashlib.sha256(b"definitely-not-a-key").digest()
    )  # a typo must not silently become the key
    assert (
        settings.fernet_key_material
        == hashlib.sha256(f"xerex-credentials::{settings.effective_secret_key}".encode()).digest()
    )


def test_key_material_parsing() -> None:
    assert parse_encryption_key(VALID_KEY_B64) == KEY_BYTES
    assert parse_encryption_key(VALID_KEY_HEX) == KEY_BYTES
    assert parse_encryption_key("") is None
    assert parse_encryption_key(None) is None
    assert parse_encryption_key("too-short") is None
    assert parse_encryption_key("z" * 64) is None  # not hexadecimal


def test_production_accepts_a_valid_configuration() -> None:
    warnings = _production().validate_runtime_security()
    assert warnings == []


# --------------------------------------------------------------------------- #
# Item 1 — bootstrap defaults
# --------------------------------------------------------------------------- #
def test_production_disables_bootstrap_by_default() -> None:
    settings = _production(bootstrap_enabled=None)
    assert settings.bootstrap_enabled_effective is False


def test_production_bootstrap_can_only_be_enabled_explicitly() -> None:
    settings = _production(bootstrap_enabled=True)
    assert settings.bootstrap_enabled_effective is True
    warnings = settings.validate_runtime_security()
    assert any("XEREX_BOOTSTRAP_ENABLED" in warning for warning in warnings)


def test_development_bootstrap_defaults_to_enabled() -> None:
    assert Settings(_env_file=None).bootstrap_enabled_effective is True


# --------------------------------------------------------------------------- #
# Item 5 — Redis and trusted proxy configuration
# --------------------------------------------------------------------------- #
def test_redis_credentials_are_injected_into_the_url() -> None:
    settings = Settings(
        _env_file=None,
        redis_url="redis://redis:6379/0",
        redis_password="p@ss word",
    )
    assert settings.redis_connection_url == "redis://:p%40ss%20word@redis:6379/0"
    assert settings.redis_auth_configured is True


def test_redis_username_and_url_credentials_are_supported() -> None:
    with_user = Settings(
        _env_file=None,
        redis_url="redis://cache:6379/1",
        redis_username="xerex",
        redis_password="secret",
    )
    assert with_user.redis_connection_url == "redis://xerex:secret@cache:6379/1"

    embedded = Settings(
        _env_file=None,
        redis_url="redis://:already-there@cache:6379/1",
        redis_password="ignored",
    )
    assert embedded.redis_connection_url == "redis://:already-there@cache:6379/1"


def test_production_warns_when_redis_has_no_authentication() -> None:
    warnings = _production(redis_password=None).validate_runtime_security()
    assert any("Redis authentication" in warning for warning in warnings)


def test_trusted_proxies_accept_ips_and_networks() -> None:
    settings = Settings(_env_file=None, trusted_proxies="10.0.0.0/8, 192.168.1.7, ")
    assert len(settings.trusted_networks) == 2
    assert settings.invalid_trusted_proxies == ()


def test_production_rejects_invalid_trusted_proxies() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(trusted_proxies=["10.0.0.0/8", "not-an-ip"])
    assert "not-an-ip" in error.value.problems["XEREX_TRUSTED_PROXIES"]


def test_empty_trusted_proxies_produce_a_warning_not_an_error() -> None:
    warnings = _production(trusted_proxies=[]).validate_runtime_security()
    assert any("XEREX_TRUSTED_PROXIES is empty" in warning for warning in warnings)


def test_wildcard_cors_origin_is_rejected_in_production() -> None:
    with pytest.raises(ConfigurationError) as error:
        _production(cors_origins=["*"])
    assert "XEREX_CORS_ORIGINS" in error.value.problems


def test_placeholder_detection_helper() -> None:
    assert looks_like_placeholder("change-me-in-production") is True
    assert looks_like_placeholder("") is True
    assert looks_like_placeholder("aaaaaaaaaaaaaaaaaaaa") is True
    assert looks_like_placeholder(VALID_SECRET) is False
