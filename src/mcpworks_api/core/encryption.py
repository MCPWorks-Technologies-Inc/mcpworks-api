"""Envelope encryption module using AES-256-GCM with KEK/DEK pattern.

All sensitive agent data (AI API keys, state values, channel configs) is encrypted
using a unique Data Encryption Key (DEK) per value. The DEK itself is encrypted
with a Key Encryption Key (KEK) loaded from the ENCRYPTION_KEK_B64 env var.

Pattern:
  plaintext → encrypt_value(plaintext) → (ciphertext, encrypted_dek)
  (ciphertext, encrypted_dek) → decrypt_value(ciphertext, encrypted_dek) → plaintext
"""

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_kek: bytes | None = None


def _get_kek() -> bytes:
    global _kek
    if _kek is None:
        from mcpworks_api.config import get_settings

        kek_b64 = get_settings().encryption_kek_b64
        if not kek_b64:
            raise RuntimeError("ENCRYPTION_KEK_B64 not configured")
        _kek = base64.b64decode(kek_b64)
        if len(_kek) != 32:
            raise RuntimeError("ENCRYPTION_KEK_B64 must decode to exactly 32 bytes")
    return _kek


def generate_dek() -> bytes:
    return os.urandom(32)


def encrypt_dek(dek: bytes, kek: bytes | None = None) -> bytes:
    kek = kek or _get_kek()
    nonce = os.urandom(12)
    aesgcm = AESGCM(kek)
    ct = aesgcm.encrypt(nonce, dek, None)
    return nonce + ct


def decrypt_dek(encrypted_dek: bytes, kek: bytes | None = None) -> bytes:
    kek = kek or _get_kek()
    nonce = encrypted_dek[:12]
    ct = encrypted_dek[12:]
    aesgcm = AESGCM(kek)
    return aesgcm.decrypt(nonce, ct, None)


def encrypt_value(plaintext: Any) -> tuple[bytes, bytes]:
    serialized = json.dumps(plaintext).encode("utf-8")
    dek = generate_dek()
    nonce = os.urandom(12)
    aesgcm = AESGCM(dek)
    ciphertext = nonce + aesgcm.encrypt(nonce, serialized, None)
    encrypted_dek = encrypt_dek(dek)
    return ciphertext, encrypted_dek


def decrypt_value(ciphertext: bytes, encrypted_dek: bytes) -> Any:
    dek = decrypt_dek(encrypted_dek)
    nonce = ciphertext[:12]
    ct = ciphertext[12:]
    aesgcm = AESGCM(dek)
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return json.loads(plaintext.decode("utf-8"))


def encrypt_string(plaintext: str) -> tuple[bytes, bytes]:
    dek = generate_dek()
    nonce = os.urandom(12)
    aesgcm = AESGCM(dek)
    ciphertext = nonce + aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    encrypted_dek = encrypt_dek(dek)
    return ciphertext, encrypted_dek


def decrypt_string(ciphertext: bytes, encrypted_dek: bytes) -> str:
    dek = decrypt_dek(encrypted_dek)
    nonce = ciphertext[:12]
    ct = ciphertext[12:]
    aesgcm = AESGCM(dek)
    return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
