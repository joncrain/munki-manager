"""Symmetric encryption for small secrets stored in the DB.

Used for things like an ``Authorization: Basic …`` header we cache on an
enrollment token so the download can include it even when the canonical
password is only stored as an Argon2 hash.

Key derivation: HKDF(SHA-256, ``settings.secret_key`` + ``purpose``) → 32 bytes
→ urlsafe-b64 → Fernet key. Rotating ``SECRET_KEY`` therefore invalidates all
ciphertexts (which is desirable: tokens are short-lived).
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from automunki.core.config import settings


def _derive_fernet_key(purpose: str) -> bytes:
    salt = hashlib.sha256(f"automunki::{purpose}".encode()).digest()
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b"automunki-secret-box-v1",
    )
    raw = hkdf.derive(settings.secret_key.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def encrypt_for(purpose: str, plaintext: str) -> str:
    """Return a urlsafe-b64 Fernet token. Empty input → empty string."""
    if not plaintext:
        return ""
    f = Fernet(_derive_fernet_key(purpose))
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_for(purpose: str, ciphertext: str) -> str | None:
    """Return the plaintext or ``None`` on any decoding/auth failure."""
    if not ciphertext:
        return None
    f = Fernet(_derive_fernet_key(purpose))
    try:
        raw = f.decrypt(ciphertext.encode("ascii"))
    except (InvalidToken, ValueError):
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
