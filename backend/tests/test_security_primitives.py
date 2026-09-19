"""Security primitives: hashing, tokens, encrypted credentials, API keys."""

from __future__ import annotations

import datetime as dt

import pytest

from app.core.crypto import decrypt_secret, encrypt_secret, key_hint
from app.core.errors import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_token,
    generate_api_key,
    hash_password,
    hash_token,
    mask_api_key,
    verify_password,
)
from app.services.rate_limit import RateLimitPolicy, ScopedRateLimiter


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$argon2id$")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_access_token_contains_expected_claims() -> None:
    issued = create_access_token("user-1", role="owner", email="owner@xerex.ai")
    payload = decode_token(issued.token, expected_type="access")
    assert payload["sub"] == "user-1"
    assert payload["role"] == "owner"
    assert payload["iss"] == "xerex-ai"
    assert payload["exp"] > dt.datetime.now(dt.UTC).timestamp()


def test_expired_token_is_rejected() -> None:
    from app.core.security import create_token

    issued = create_token("user-1", "access", expires_delta=dt.timedelta(seconds=-5))
    with pytest.raises(AuthenticationError) as excinfo:
        decode_token(issued.token, expected_type="access")
    assert excinfo.value.code == "token_expired"


def test_refresh_tokens_are_stored_hashed() -> None:
    first = hash_token("token-a")
    second = hash_token("token-b")
    assert first != second
    assert len(first) == 64


def test_credential_encryption_roundtrip_and_hint() -> None:
    secret = "sk-live-super-secret-value-1234"
    encrypted = encrypt_secret(secret)
    assert secret not in encrypted
    assert decrypt_secret(encrypted) == secret
    assert key_hint(secret) == "…1234"

    # Tampering must be detected (AES-GCM authentication tag).
    with pytest.raises(Exception):  # noqa: B017 - EncryptionError
        decrypt_secret(encrypted[:-4] + "AAAA")


def test_api_key_generation_and_masking() -> None:
    full_key, prefix, hashed = generate_api_key()
    assert full_key.startswith("xrx_live_")
    assert prefix.startswith("xrx_live_")
    assert full_key.startswith(prefix)
    assert len(hashed) == 64
    assert mask_api_key(prefix).endswith("…")


async def test_rate_limiter_fails_open_without_redis() -> None:
    limiter = ScopedRateLimiter(
        policy=RateLimitPolicy(name="unit", scope_kind="login", limit=1, window_seconds=60)
    )
    result = await limiter.hit("subject")
    assert result.allowed is True
    assert result.backend == "bypassed"
