"""Symmetric encryption helpers for storing secrets at rest."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        key = settings.encryption_key or settings.email_token_encryption_key
        if not key:
            raise ValueError(
                "ENCRYPTION_KEY (or EMAIL_TOKEN_ENCRYPTION_KEY) must be set. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(key.encode())
    return _fernet


def encrypt_token(plaintext: str) -> str:
    """Encrypt a token string and return the Fernet ciphertext as a string."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted token string."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        raise ValueError("Failed to decrypt token — encryption key may have changed.")
