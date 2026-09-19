"""Application configuration.

All configuration keys, environment variables and identifiers are English by
design (see PROMPT.md section 10). Persian exists only in the presentation layer
of the admin panel.

Security posture
----------------

* **Development / test** — everything works out of the box: secrets are generated
  or derived so a fresh checkout boots without ceremony.
* **Staging / production** — nothing is generated or derived silently. The
  application refuses to start unless ``XEREX_SECRET_KEY`` and
  ``XEREX_CREDENTIALS_ENCRYPTION_KEY`` are provided explicitly and look like real
  key material, and first-run bootstrap stays disabled unless it is explicitly
  enabled.

``validate_runtime_security()`` is executed while the application is created, so a
misconfigured deployment fails fast at startup instead of running insecurely.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from functools import lru_cache
from ipaddress import IPv4Network, IPv6Network, ip_network
from typing import Annotated, Literal
from urllib.parse import quote, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]

#: Environments where generated defaults are allowed. Staging is treated like
#: production on purpose: it is reachable by real people.
_GENERATED_DEFAULTS_ALLOWED = frozenset({"development", "test"})

MIN_SECRET_KEY_LENGTH = 32
ENCRYPTION_KEY_BYTES = 32
_HEX_KEY_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")

#: Values that must never protect a real deployment.
_PLACEHOLDER_SECRETS = frozenset(
    {
        "change-me",
        "change-me-in-production",
        "changeme",
        "change_me",
        "default",
        "example",
        "insecure",
        "password",
        "placeholder",
        "secret",
        "secret-key",
        "your-secret-key",
    }
)
_PLACEHOLDER_MARKERS = ("change-me", "changeme", "placeholder", "example", "insecure", "your-")

TrustedNetwork = IPv4Network | IPv6Network


class ConfigurationError(RuntimeError):
    """Raised at startup when the deployment configuration is unsafe.

    ``problems`` maps an environment variable name to the reason it was rejected,
    so operators get one complete report instead of a series of restarts.
    """

    def __init__(self, problems: dict[str, str]) -> None:
        self.problems = dict(problems)
        summary = "; ".join(f"{key}: {reason}" for key, reason in self.problems.items())
        super().__init__(f"Unsafe production configuration -> {summary}")


def looks_like_placeholder(value: str) -> bool:
    """True when a secret is an obvious placeholder, default or low-entropy value."""
    normalized = value.strip().lower()
    if not normalized:
        return True
    if normalized in _PLACEHOLDER_SECRETS:
        return True
    if any(marker in normalized for marker in _PLACEHOLDER_MARKERS):
        return True
    # `aaaaaaaa...`, `1234567890...` and similar single-character repeats.
    return len(set(normalized)) < 6


def parse_encryption_key(value: str | None) -> bytes | None:
    """Return 32 bytes of AES key material, or ``None`` when the value is invalid.

    Accepted forms (nothing else, so a typo can never silently weaken encryption):

    * url-safe base64 of exactly 32 bytes (``base64.urlsafe_b64encode(os.urandom(32))``);
    * exactly 64 hexadecimal characters.
    """
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    padded = raw + "=" * (-len(raw) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError, UnicodeEncodeError):
        decoded = b""
    if len(decoded) == ENCRYPTION_KEY_BYTES:
        return decoded
    if _HEX_KEY_PATTERN.match(raw):
        return bytes.fromhex(raw)
    return None


def _redis_url_has_credentials(url: str) -> bool:
    try:
        netloc = urlsplit(url).netloc
    except ValueError:
        return False
    return "@" in netloc


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
    milestone: str = "M7"
    environment: Environment = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # --- Security ----------------------------------------------------------
    # ``None`` means "not configured": development and test generate one, every
    # other environment refuses to start until it is provided explicitly.
    secret_key: str | None = None
    credentials_encryption_key: str | None = None
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    # ``None`` means "follow the environment default": enabled in development and
    # test, disabled in staging and production.
    bootstrap_enabled: bool | None = None
    password_min_length: int = 10
    login_rate_limit_attempts: int = 10
    login_rate_limit_window_seconds: int = 300
    # Reverse proxies whose ``X-Forwarded-For`` header may be trusted. Empty means
    # "trust nothing": the direct peer address is used and cannot be spoofed.
    trusted_proxies: Annotated[list[str], NoDecode] = Field(default_factory=list)
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
    redis_username: str | None = None
    redis_password: str | None = None
    redis_required: bool = False
    redis_socket_timeout_seconds: float = 1.5
    rate_limit_enabled: bool = True

    # --- Gateway (public /v1 surface) --------------------------------------
    gateway_enabled: bool = True
    #: Hard ceiling for one client request across every failover attempt.
    gateway_request_deadline_seconds: float = 60.0
    #: Default per-key limit used when a key does not carry its own value.
    gateway_default_rate_limit_per_min: int = 60

    # --- Health checks (M5) ------------------------------------------------
    #: Scheduled upstream checks are opt-in: a timer that probes every provider on
    #: every deployment would be a surprise (and a cost).
    health_scheduler_enabled: bool = False
    health_check_interval_seconds: int = 300
    health_history_limit: int = 200

    # --- Localization ------------------------------------------------------
    default_locale: str = "fa"
    supported_locales: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["fa", "en"])
    default_timezone: str = "Asia/Tehran"

    # --- Observability -----------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False
    expose_planned_endpoints: bool = True

    # ----------------------------------------------------------------------
    @field_validator("cors_origins", "supported_locales", "trusted_proxies", mode="before")
    @classmethod
    def _split_csv_or_json(cls, value: object) -> object:
        """Accept both JSON arrays (``["a","b"]``) and comma separated strings."""
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            if raw.startswith("["):
                return json.loads(raw)
            return [item.strip() for item in raw.split(",") if item.strip()]
        return value

    @field_validator("bootstrap_enabled", mode="before")
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        """An empty ``XEREX_BOOTSTRAP_ENABLED=`` means "use the environment default"."""
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("api_v1_prefix")
    @classmethod
    def _normalize_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/")

    @model_validator(mode="after")
    def _ensure_deployable(self) -> Settings:
        """Fail fast: constructing settings for a deployed environment validates them."""
        if not self.is_development_like:
            self.validate_runtime_security()
        return self

    # ----------------------------------------------------------------------
    # Derived configuration
    # ----------------------------------------------------------------------
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development_like(self) -> bool:
        return self.environment in _GENERATED_DEFAULTS_ALLOWED

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def bootstrap_configured_explicitly(self) -> bool:
        return self.bootstrap_enabled is not None

    @property
    def bootstrap_enabled_effective(self) -> bool:
        """First-run setup switch: explicit value wins, otherwise environment default."""
        if self.bootstrap_enabled is not None:
            return self.bootstrap_enabled
        return self.is_development_like

    @property
    def effective_secret_key(self) -> str:
        """JWT signing key.

        Development and test generate a process-local key when none is provided;
        any other environment has already failed startup validation instead.
        """
        if self.secret_key and self.secret_key.strip():
            return self.secret_key.strip()
        if not self.is_development_like:
            raise ConfigurationError(
                {"XEREX_SECRET_KEY": "a generated secret is only allowed in development or test"}
            )
        return _derived_secret_key()

    @property
    def encryption_key_is_derived(self) -> bool:
        """True when provider credentials fall back to a key derived from the JWT secret."""
        return parse_encryption_key(self.credentials_encryption_key) is None

    @property
    def fernet_key_material(self) -> bytes:
        """Deterministic 32-byte AES-GCM key material for provider credentials.

        A dedicated ``XEREX_CREDENTIALS_ENCRYPTION_KEY`` always wins. The derived
        fallback exists only for development and test; every other environment
        fails startup validation before this property is reached.
        """
        material = parse_encryption_key(self.credentials_encryption_key)
        if material is not None:
            return material
        if not self.is_development_like:
            raise ConfigurationError(
                {
                    "XEREX_CREDENTIALS_ENCRYPTION_KEY": (
                        "a key derived from the JWT secret is only allowed in development or test"
                    )
                }
            )
        return hashlib.sha256(f"xerex-credentials::{self.effective_secret_key}".encode()).digest()

    @property
    def trusted_networks(self) -> tuple[TrustedNetwork, ...]:
        """Parsed trusted proxy networks (bare addresses are treated as /32 or /128)."""
        networks: list[TrustedNetwork] = []
        for entry in self.trusted_proxies:
            candidate = entry.strip()
            if not candidate:
                continue
            try:
                networks.append(ip_network(candidate, strict=False))
            except ValueError:
                continue
        return tuple(networks)

    @property
    def invalid_trusted_proxies(self) -> tuple[str, ...]:
        """Entries of ``XEREX_TRUSTED_PROXIES`` that are not valid IPs or CIDR blocks."""
        invalid: list[str] = []
        for entry in self.trusted_proxies:
            candidate = entry.strip()
            if not candidate:
                continue
            try:
                ip_network(candidate, strict=False)
            except ValueError:
                invalid.append(candidate)
        return tuple(invalid)

    @property
    def redis_connection_url(self) -> str:
        """Redis URL including credentials configured through the environment.

        Credentials already embedded in ``XEREX_REDIS_URL`` are left untouched;
        otherwise ``XEREX_REDIS_USERNAME`` / ``XEREX_REDIS_PASSWORD`` are injected
        so no password ever has to be hard-coded in a connection string.
        """
        if not (self.redis_username or self.redis_password):
            return self.redis_url
        if _redis_url_has_credentials(self.redis_url):
            return self.redis_url
        parts = urlsplit(self.redis_url)
        user = quote(self.redis_username or "", safe="")
        password = quote(self.redis_password or "", safe="")
        netloc = f"{user}:{password}@{parts.netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    @property
    def redis_auth_configured(self) -> bool:
        return bool(self.redis_password) or _redis_url_has_credentials(self.redis_url)

    # ----------------------------------------------------------------------
    # Startup validation
    # ----------------------------------------------------------------------
    def validate_runtime_security(self) -> list[str]:
        """Validate deployment safety.

        Returns human readable warnings; raises :class:`ConfigurationError` listing
        every blocking problem. Development and test are never blocked, so local
        usability is preserved.
        """
        if self.is_development_like:
            return []

        problems: dict[str, str] = {}
        warnings: list[str] = []

        # 1. JWT / application secret ---------------------------------------
        secret = (self.secret_key or "").strip()
        if not secret:
            problems["XEREX_SECRET_KEY"] = (
                "must be provided explicitly in a deployed environment; generate one "
                'with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        elif looks_like_placeholder(secret):
            problems["XEREX_SECRET_KEY"] = (
                "looks like a placeholder, default or low-entropy value; generate a random secret"
            )
        elif len(secret) < MIN_SECRET_KEY_LENGTH:
            problems["XEREX_SECRET_KEY"] = (
                f"must be at least {MIN_SECRET_KEY_LENGTH} characters long"
            )

        # 2. Provider credential encryption key ------------------------------
        raw_encryption_key = (self.credentials_encryption_key or "").strip()
        encryption_key = parse_encryption_key(raw_encryption_key)
        if not raw_encryption_key:
            problems["XEREX_CREDENTIALS_ENCRYPTION_KEY"] = (
                "must be provided explicitly in a deployed environment; the key is never "
                "derived from XEREX_SECRET_KEY outside development and test. Generate one "
                'with: python -c "import base64,os;'
                ' print(base64.urlsafe_b64encode(os.urandom(32)).decode())"'
            )
        elif encryption_key is None:
            problems["XEREX_CREDENTIALS_ENCRYPTION_KEY"] = (
                "must be 32 bytes of url-safe base64 or 64 hexadecimal characters"
            )
        elif secret and (
            raw_encryption_key == secret or parse_encryption_key(secret) == encryption_key
        ):
            problems["XEREX_CREDENTIALS_ENCRYPTION_KEY"] = "must be different from XEREX_SECRET_KEY"

        # 3. First-run bootstrap ---------------------------------------------
        if self.bootstrap_enabled is True:
            warnings.append(
                "XEREX_BOOTSTRAP_ENABLED is explicitly enabled: anyone who reaches the panel "
                "first can create the owner account. Disable it once the owner exists."
            )

        # 4. CORS --------------------------------------------------------------
        if "*" in self.cors_origins:
            problems["XEREX_CORS_ORIGINS"] = (
                "must not contain '*' while credentials (cookies) are allowed; list the exact "
                "panel origins instead"
            )

        # 5. Trusted proxies ---------------------------------------------------
        invalid_proxies = self.invalid_trusted_proxies
        if invalid_proxies:
            problems["XEREX_TRUSTED_PROXIES"] = (
                "contains entries that are not valid IP addresses or CIDR blocks: "
                + ", ".join(invalid_proxies)
            )
        elif not self.trusted_proxies:
            warnings.append(
                "XEREX_TRUSTED_PROXIES is empty: X-Forwarded-For is ignored and the proxy "
                "address is recorded as the client. Set it to the reverse proxy network when "
                "the API runs behind one."
            )

        # 6. Redis -------------------------------------------------------------
        if not self.redis_auth_configured:
            warnings.append(
                "Redis authentication is not configured (XEREX_REDIS_PASSWORD or credentials "
                "inside XEREX_REDIS_URL). Keep Redis on a private network if that is intended."
            )

        # 7. Development affordances left on --------------------------------
        if self.debug:
            warnings.append("XEREX_DEBUG is enabled in a deployed environment.")

        if problems:
            raise ConfigurationError(problems)
        return warnings

    def database_connect_args(self) -> dict[str, object]:
        """Driver specific connection arguments (SQLite needs no pooling args)."""
        if self.is_sqlite:
            return {}
        return {
            "server_settings": {"application_name": "xerex-ai-api"},
            "timeout": 10,
        }


_DERIVED_SECRET: str | None = None


def _derived_secret_key() -> str:
    """Process-local secret for development and test when none is configured."""
    global _DERIVED_SECRET
    if _DERIVED_SECRET is None:
        import secrets

        _DERIVED_SECRET = secrets.token_urlsafe(48)
    return _DERIVED_SECRET


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
