"""Application configuration.

All configuration keys, environment variables and identifiers are English by
design (see PROMPT.md section 10). Persian exists only in the presentation layer
of the admin panel.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="XEREX_",
        env_file=(".env", ".env.local", "../.env", "../.env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------------
    app_name: str = "Xerex AI"
    app_version: str = "0.1.0"
    milestone: str = "M1"
    environment: Environment = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # --- Security ----------------------------------------------------------
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    credentials_encryption_key: str | None = None
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    bootstrap_enabled: bool = True
    password_min_length: int = 10
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 300
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # --- Database ----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://xerex:xerex@localhost:5432/xerex"
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20

    # --- Redis -------------------------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    redis_required: bool = False
    redis_socket_timeout_seconds: float = 1.5
    rate_limit_enabled: bool = True

    # --- Localization ------------------------------------------------------
    default_locale: str = "fa"
    supported_locales: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["fa", "en"])
    default_timezone: str = "Asia/Tehran"

    # --- Observability -----------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False
    expose_planned_endpoints: bool = True

    # ----------------------------------------------------------------------
    @field_validator("cors_origins", "supported_locales", mode="before")
    @classmethod
    def _split_csv_or_json(cls, value: object) -> object:
        """Accept both JSON arrays (``["a","b"]``) and comma separated strings."""
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("["):
                return json.loads(raw)
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def _normalize_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/")

    # ----------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def fernet_key_material(self) -> bytes:
        """Deterministic 32-byte AES-GCM key material.

        Falls back to deriving from ``secret_key`` so that a development
        environment works out of the box, while production is expected to
        provide ``XEREX_CREDENTIALS_ENCRYPTION_KEY`` explicitly.
        """
        if self.credentials_encryption_key:
            raw = self.credentials_encryption_key.strip()
            try:
                decoded = base64.urlsafe_b64decode(raw)
                if len(decoded) == 32:
                    return decoded
            except Exception:  # noqa: BLE001 - fall back to hashing
                pass
            return hashlib.sha256(raw.encode("utf-8")).digest()
        return hashlib.sha256(f"xerex-credentials::{self.secret_key}".encode()).digest()

    def database_connect_args(self) -> dict[str, object]:
        """Driver specific connection arguments (SQLite needs no pooling args)."""
        if self.is_sqlite:
            return {}
        return {
            "server_settings": {"application_name": "xerex-ai-api"},
            "timeout": 10,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
