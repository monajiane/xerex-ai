"""Redaction of secrets before they reach logs or audit storage.

Two rules, both enforced by tests:

* provider credentials, API keys, passwords, refresh tokens and encryption keys
  never appear in log output, in error envelopes or in audit ``diff`` payloads;
* redaction is *key based* and **recursive**, so nested dictionaries and lists get
  the same treatment as flat mappings.

The module is deliberately dependency free (no logging, no database) so it can be
imported from anywhere, including configuration validation.
"""

from __future__ import annotations

from typing import Any

REDACTED = "[redacted]"

#: Substrings that mark a key as sensitive. Matching is case-insensitive and
#: substring based, so ``provider_secret``, ``apiKey`` and ``xerex_secret_key``
#: are all covered.
SENSITIVE_KEY_MARKERS: tuple[str, ...] = (
    "secret",
    "password",
    "passwd",
    "token",
    "credential",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "access_key",
    "cookie",
    "session",
)

#: Keys that merely *contain* a marker but are safe and useful to keep verbatim
#: (they describe secrets instead of carrying them).
SAFE_KEY_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "key_hint",
        "credential_count",
        "credential_id",
        "credentials_encryption_key_configured",
        "token_type",
        "token_ttl_seconds",
        "access_token_expires_in",
        "refresh_token_ttl_days",
        "password_min_length",
        "session_count",
    }
)


def is_sensitive_key(key: str) -> bool:
    lowered = key.strip().lower()
    if lowered in SAFE_KEY_EXCEPTIONS:
        return False
    return any(marker in lowered for marker in SENSITIVE_KEY_MARKERS)


def redact(value: Any) -> Any:
    """Recursively replace sensitive values with ``[redacted]``."""
    if isinstance(value, dict):
        return {
            key: (REDACTED if is_sensitive_key(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, set):
        return {redact(item) for item in value}
    return value


def redact_text(value: str) -> str:
    """Best-effort scrub of long opaque tokens inside free-form text."""
    parts = value.split()
    scrubbed: list[str] = []
    for part in parts:
        lowered = part.lower()
        if any(marker in lowered for marker in ("sk-", "xrx_live_", "bearer")) and len(part) > 12:
            scrubbed.append(REDACTED)
        else:
            scrubbed.append(part)
    return " ".join(scrubbed)
