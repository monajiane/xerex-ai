"""Password hashing, JWT issuing/verification and API key primitives.

Everything here is English and framework agnostic so it can be reused later by
the gateway (downstream ``xrx_live_...`` keys) and by background workers.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import AuthenticationError
from app.core.logging import get_logger

logger = get_logger(__name__)

TokenType = Literal["access", "refresh"]

_password_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=19456,  # ~19 MiB, Argon2id interactive profile
    parallelism=1,
    hash_len=32,
    salt_len=16,
)

API_KEY_PREFIX = "xrx_live"
API_KEY_DISPLAY_LENGTH = 8
JWT_ALGORITHM = "HS256"


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --------------------------------------------------------------------------- #
# Tokens
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class IssuedToken:
    token: str
    token_type: TokenType
    expires_at: datetime
    jti: str


def create_token(
    subject: str,
    token_type: TokenType,
    *,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> IssuedToken:
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    jti = secrets.token_urlsafe(24)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": "xerex-ai",
    }
    if extra_claims:
        payload.update(extra_claims)
    token = jwt.encode(payload, settings.effective_secret_key, algorithm=JWT_ALGORITHM)
    return IssuedToken(token=token, token_type=token_type, expires_at=expires_at, jti=jti)


def create_access_token(subject: str, *, role: str, email: str) -> IssuedToken:
    return create_token(
        subject,
        "access",
        expires_delta=timedelta(minutes=settings.access_token_ttl_minutes),
        extra_claims={"role": role, "email": email},
    )


def create_refresh_token(subject: str) -> IssuedToken:
    return create_token(
        subject,
        "refresh",
        expires_delta=timedelta(days=settings.refresh_token_ttl_days),
    )


def decode_token(token: str, *, expected_type: TokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.effective_secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "sub", "jti"]},
            issuer="xerex-ai",
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("The token has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("The token is invalid.", code="token_invalid") from exc

    if expected_type is not None and payload.get("type") != expected_type:
        raise AuthenticationError("The token type is not accepted here.", code="token_type_invalid")
    return payload


def hash_token(token: str) -> str:
    """Refresh tokens are stored hashed; the raw value never touches the DB."""
    return hashlib.sha256(f"{settings.effective_secret_key}:{token}".encode()).hexdigest()


def constant_time_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


# --------------------------------------------------------------------------- #
# Downstream API keys (used from M4 onwards)
# --------------------------------------------------------------------------- #
def generate_api_key() -> tuple[str, str, str]:
    """Return ``(full_key, prefix, hashed_key)`` for a downstream API key."""
    secret = secrets.token_urlsafe(32)
    prefix = f"{API_KEY_PREFIX}_{secrets.token_hex(4)}"
    full_key = f"{prefix}_{secret}"
    return full_key, prefix, hash_api_key(full_key)


def hash_api_key(full_key: str) -> str:
    return hashlib.sha256(full_key.encode()).hexdigest()


def mask_api_key(prefix: str) -> str:
    """Display form, e.g. ``xrx_live_8f2a…``."""
    return f"{prefix}…"
