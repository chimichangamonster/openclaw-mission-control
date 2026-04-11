"""Symmetric encryption helpers for storing secrets at rest.

Uses AES-256-GCM (authenticated encryption) with key versioning for rotation.
Backward-compatible: transparently decrypts legacy Fernet ciphertexts during
migration period.

Wire format (v1):
    "v1:" + base64( key_version[1] + nonce[12] + ciphertext[N] + tag[16] )

Key derivation:
    HKDF-SHA256(master_key, info=b"aes256gcm-v<version>") -> 256-bit key
"""

from __future__ import annotations

import os
import struct
from base64 import urlsafe_b64decode, urlsafe_b64encode

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_V1_PREFIX = "v1:"
_NONCE_BYTES = 12  # 96-bit nonce (GCM standard)
_KEY_BYTES = 32  # 256-bit key
_TAG_BYTES = 16  # 128-bit auth tag (appended by AESGCM)
_VERSION_BYTES = 1  # supports up to 255 key versions

# Current key version — bump when rotating keys
CURRENT_KEY_VERSION: int = 1

# ---------------------------------------------------------------------------
# Internal state (lazy-initialized)
# ---------------------------------------------------------------------------

_keys: dict[int, AESGCM] = {}
_fernet: Fernet | None = None


def _get_master_key() -> bytes:
    """Return the raw master key bytes from settings."""
    raw = settings.encryption_key or settings.email_token_encryption_key
    if not raw:
        raise ValueError(
            "ENCRYPTION_KEY must be set. "
            'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    return raw.encode()


def _derive_aes_key(master_key: bytes, version: int) -> bytes:
    """Derive a 256-bit AES key from the master key using HKDF-SHA256."""
    return HKDF(
        algorithm=SHA256(),
        length=_KEY_BYTES,
        salt=None,
        info=f"aes256gcm-v{version}".encode(),
    ).derive(master_key)


def _get_aesgcm(version: int | None = None) -> tuple[AESGCM, int]:
    """Return (AESGCM cipher, version) for the given or current version."""
    ver = version if version is not None else CURRENT_KEY_VERSION
    if ver not in _keys:
        derived = _derive_aes_key(_get_master_key(), ver)
        _keys[ver] = AESGCM(derived)
    return _keys[ver], ver


def _get_fernet() -> Fernet:
    """Lazy-init Fernet for decrypting legacy ciphertexts."""
    global _fernet
    if _fernet is None:
        key = settings.encryption_key or settings.email_token_encryption_key
        if not key:
            raise ValueError("ENCRYPTION_KEY must be set for legacy Fernet decryption.")
        # Fernet keys are url-safe base64; if the master key isn't a valid
        # Fernet key we can't decrypt legacy data — that's expected after
        # a full migration to AES-256-GCM.
        _fernet = Fernet(key.encode())
    return _fernet


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def encrypt_token(plaintext: str) -> str:
    """Encrypt a string using AES-256-GCM. Returns a versioned ciphertext."""
    cipher, ver = _get_aesgcm()
    nonce = os.urandom(_NONCE_BYTES)
    ct = cipher.encrypt(nonce, plaintext.encode(), None)  # ct includes tag
    # Pack: version(1) + nonce(12) + ciphertext+tag(N+16)
    blob = struct.pack("B", ver) + nonce + ct
    return _V1_PREFIX + urlsafe_b64encode(blob).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a token — supports both AES-256-GCM (v1:) and legacy Fernet."""
    if ciphertext.startswith(_V1_PREFIX):
        return _decrypt_v1(ciphertext)
    # Legacy Fernet fallback
    return _decrypt_fernet(ciphertext)


def _decrypt_v1(ciphertext: str) -> str:
    """Decrypt an AES-256-GCM v1 ciphertext."""
    raw = urlsafe_b64decode(ciphertext[len(_V1_PREFIX) :])
    if len(raw) < _VERSION_BYTES + _NONCE_BYTES + _TAG_BYTES:
        raise ValueError("Ciphertext too short — corrupted or truncated.")
    version = struct.unpack("B", raw[:_VERSION_BYTES])[0]
    nonce = raw[_VERSION_BYTES : _VERSION_BYTES + _NONCE_BYTES]
    ct_and_tag = raw[_VERSION_BYTES + _NONCE_BYTES :]
    cipher, _ = _get_aesgcm(version)
    try:
        plaintext = cipher.decrypt(nonce, ct_and_tag, None)
    except Exception:
        raise ValueError(
            f"Failed to decrypt token (key version {version}) " "— encryption key may have changed."
        )
    return plaintext.decode()


def _decrypt_fernet(ciphertext: str) -> str:
    """Decrypt a legacy Fernet ciphertext."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        raise ValueError("Failed to decrypt token — encryption key may have changed.")


def re_encrypt(ciphertext: str) -> str | None:
    """Re-encrypt a ciphertext to the current AES-256-GCM format.

    Returns the new ciphertext if re-encryption was needed, or None if the
    token is already on the current version.
    """
    if ciphertext.startswith(_V1_PREFIX):
        raw = urlsafe_b64decode(ciphertext[len(_V1_PREFIX) :])
        version = struct.unpack("B", raw[:_VERSION_BYTES])[0]
        if version == CURRENT_KEY_VERSION:
            return None  # already current
    # Decrypt (any format) and re-encrypt with current key
    plaintext = decrypt_token(ciphertext)
    return encrypt_token(plaintext)


def reset_cache() -> None:
    """Clear cached keys — useful for tests that swap settings."""
    global _fernet
    _keys.clear()
    _fernet = None
