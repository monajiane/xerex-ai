"""Symmetric encryption for provider credentials (AES-256-GCM).

Provider secrets are encrypted at rest and are never returned in plaintext by
the API after creation (PROMPT.md section 7).
"""

from __future__ import annotations

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.errors import AppError

_NONCE_BYTES = 12


class EncryptionError(AppError):
    status_code = 500
    code = "encryption_error"
    message = "Stored secret could not be processed."


def _cipher() -> AESGCM:
    return AESGCM(settings.fernet_key_material)


def encrypt_secret(plaintext: str) -> str:
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = _cipher().encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(payload: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        nonce, ciphertext = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return _cipher().decrypt(nonce, ciphertext, None).decode("utf-8")
    except (InvalidTag, ValueError, TypeError) as exc:
        raise EncryptionError() from exc


def key_hint(secret: str, *, visible: int = 4) -> str:
    """Non-reversible display hint, e.g. ``sk-…a91f``."""
    cleaned = secret.strip()
    if len(cleaned) <= visible:
        return "…"
    return f"…{cleaned[-visible:]}"
