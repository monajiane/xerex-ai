"""Symmetric encryption for provider credentials (AES-256-GCM).

Provider secrets are encrypted at rest and are never returned in plaintext by
the API after creation (PROMPT.md section 7).

Key management
--------------

* The key is ``XEREX_CREDENTIALS_ENCRYPTION_KEY``: 32 bytes of url-safe base64 or
  64 hexadecimal characters. Anything else is rejected by configuration
  validation instead of being silently hashed into something weaker.
* Development and test may omit it and fall back to a key derived from
  ``XEREX_SECRET_KEY``; staging and production refuse to start without a
  dedicated key.
* **Rotation (documented, not implemented).** Rotating the key is not destructive
  because every ciphertext is self-contained: ``nonce || ciphertext``. A future
  maintenance task can therefore decrypt the existing ``provider_credentials``
  rows with the old key and re-encrypt them with the new one, in one transaction
  per row, without touching any other table. Until a key *version* column exists,
  rotation is an offline operation: put the panel in maintenance, run the
  re-encryption, swap the key, restart. The helper :func:`key_fingerprint` exists
  so operators can verify which key encrypted a deployment without ever logging
  the key itself.
"""

from __future__ import annotations

import base64
import hashlib
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
    """AES-GCM cipher bound to the configured credential key.

    Raises ``ConfigurationError`` when the key is missing in a deployed
    environment: credentials must never be written with a derived key there.
    """
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


def key_fingerprint() -> str:
    """Short, non-reversible identifier of the active credential key.

    Safe to log: it is a truncated hash of already-derived key material and cannot
    be used to recover the key. Lets operators confirm which key a deployment uses
    before a rotation.
    """
    return hashlib.sha256(settings.fernet_key_material).hexdigest()[:12]


def key_hint(secret: str, *, visible: int = 4) -> str:
    """Non-reversible display hint, e.g. ``sk-…a91f``."""
    cleaned = secret.strip()
    if len(cleaned) <= visible:
        return "…"
    return f"…{cleaned[-visible:]}"
