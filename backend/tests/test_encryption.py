# ruff: noqa: INP001
"""Tests for AES-256-GCM encryption module.

Covers: encrypt/decrypt round-trip, key versioning, Fernet backward
compatibility, re-encryption, error handling, and key isolation.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

import app.core.encryption as enc

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(key: str = "test-master-key-for-aes256"):
    """Create a mock settings object with the given encryption key."""
    return type("S", (), {"encryption_key": key, "email_token_encryption_key": ""})()


@pytest.fixture(autouse=True)
def _reset():
    """Reset encryption caches before and after each test."""
    enc.reset_cache()
    yield
    enc.reset_cache()


# ---------------------------------------------------------------------------
# AES-256-GCM encrypt / decrypt
# ---------------------------------------------------------------------------


class TestAES256GCM:

    def test_round_trip(self):
        with patch("app.core.encryption.settings", _make_settings()):
            ct = enc.encrypt_token("hello world")
            assert ct.startswith("v1:")
            assert enc.decrypt_token(ct) == "hello world"

    def test_empty_string(self):
        with patch("app.core.encryption.settings", _make_settings()):
            ct = enc.encrypt_token("")
            assert enc.decrypt_token(ct) == ""

    def test_unicode(self):
        with patch("app.core.encryption.settings", _make_settings()):
            text = "日本語テスト 🔐 émojis"
            ct = enc.encrypt_token(text)
            assert enc.decrypt_token(ct) == text

    def test_long_plaintext(self):
        with patch("app.core.encryption.settings", _make_settings()):
            text = "A" * 100_000
            ct = enc.encrypt_token(text)
            assert enc.decrypt_token(ct) == text

    def test_different_ciphertexts_each_call(self):
        """Each encryption produces unique nonce → unique ciphertext."""
        with patch("app.core.encryption.settings", _make_settings()):
            ct1 = enc.encrypt_token("same")
            ct2 = enc.encrypt_token("same")
            assert ct1 != ct2
            assert enc.decrypt_token(ct1) == enc.decrypt_token(ct2) == "same"

    def test_wrong_key_fails(self):
        with patch("app.core.encryption.settings", _make_settings("key-one")):
            ct = enc.encrypt_token("secret")
        enc.reset_cache()
        with patch("app.core.encryption.settings", _make_settings("key-two")):
            with pytest.raises(ValueError, match="Failed to decrypt"):
                enc.decrypt_token(ct)

    def test_encrypt_bytes_round_trip(self):
        with patch("app.core.encryption.settings", _make_settings()):
            blob = enc.encrypt_bytes(b"\x00\x01\x02binary\xffstream")
            assert enc.decrypt_bytes(blob) == b"\x00\x01\x02binary\xffstream"

    def test_encrypt_bytes_tamper_detected(self):
        with patch("app.core.encryption.settings", _make_settings()):
            blob = bytearray(enc.encrypt_bytes(b"hello"))
            blob[-1] ^= 0xFF  # flip last byte of auth tag
            with pytest.raises(ValueError, match="Failed to decrypt"):
                enc.decrypt_bytes(bytes(blob))

    def test_truncated_ciphertext_fails(self):
        with patch("app.core.encryption.settings", _make_settings()):
            ct = enc.encrypt_token("test")
            # Truncate the base64 payload
            truncated = "v1:" + ct[3:10]
            with pytest.raises(ValueError):
                enc.decrypt_token(truncated)

    def test_tampered_ciphertext_fails(self):
        with patch("app.core.encryption.settings", _make_settings()):
            ct = enc.encrypt_token("test")
            # Flip a character in the base64 payload
            chars = list(ct)
            idx = 5  # somewhere in the base64 part
            chars[idx] = "A" if chars[idx] != "A" else "B"
            tampered = "".join(chars)
            with pytest.raises(ValueError):
                enc.decrypt_token(tampered)


# ---------------------------------------------------------------------------
# Fernet backward compatibility
# ---------------------------------------------------------------------------


class TestFernetCompat:

    def test_decrypt_legacy_fernet(self):
        """Ciphertexts without v1: prefix are decrypted via Fernet."""
        fernet_key = Fernet.generate_key().decode()
        fernet = Fernet(fernet_key.encode())
        legacy_ct = fernet.encrypt(b"legacy-secret").decode()

        with patch("app.core.encryption.settings", _make_settings(fernet_key)):
            assert enc.decrypt_token(legacy_ct) == "legacy-secret"

    def test_fernet_wrong_key_fails(self):
        fernet_key_a = Fernet.generate_key().decode()
        fernet_key_b = Fernet.generate_key().decode()
        fernet = Fernet(fernet_key_a.encode())
        legacy_ct = fernet.encrypt(b"secret").decode()

        with patch("app.core.encryption.settings", _make_settings(fernet_key_b)):
            with pytest.raises(ValueError, match="Failed to decrypt"):
                enc.decrypt_token(legacy_ct)


# ---------------------------------------------------------------------------
# Re-encryption
# ---------------------------------------------------------------------------


class TestReEncrypt:

    def test_re_encrypt_fernet_to_aes256(self):
        """re_encrypt() converts Fernet → AES-256-GCM."""
        fernet_key = Fernet.generate_key().decode()
        fernet = Fernet(fernet_key.encode())
        legacy_ct = fernet.encrypt(b"my-api-key").decode()

        with patch("app.core.encryption.settings", _make_settings(fernet_key)):
            new_ct = enc.re_encrypt(legacy_ct)
            assert new_ct is not None
            assert new_ct.startswith("v1:")
            assert enc.decrypt_token(new_ct) == "my-api-key"

    def test_re_encrypt_already_current_returns_none(self):
        with patch("app.core.encryption.settings", _make_settings()):
            ct = enc.encrypt_token("already-current")
            assert enc.re_encrypt(ct) is None

    def test_re_encrypt_preserves_plaintext(self):
        fernet_key = Fernet.generate_key().decode()
        fernet = Fernet(fernet_key.encode())
        original = "sk-or-v1-abc123"
        legacy_ct = fernet.encrypt(original.encode()).decode()

        with patch("app.core.encryption.settings", _make_settings(fernet_key)):
            new_ct = enc.re_encrypt(legacy_ct)
            assert enc.decrypt_token(new_ct) == original


# ---------------------------------------------------------------------------
# Key versioning
# ---------------------------------------------------------------------------


class TestKeyVersioning:

    def test_ciphertext_contains_version_byte(self):
        with patch("app.core.encryption.settings", _make_settings()):
            ct = enc.encrypt_token("versioned")
            assert ct.startswith("v1:")

    def test_version_in_binary(self):
        """Version byte in the decoded blob matches CURRENT_KEY_VERSION."""
        import struct
        from base64 import urlsafe_b64decode

        with patch("app.core.encryption.settings", _make_settings()):
            ct = enc.encrypt_token("check-version")
            raw = urlsafe_b64decode(ct[3:])
            version = struct.unpack("B", raw[:1])[0]
            assert version == enc.CURRENT_KEY_VERSION


# ---------------------------------------------------------------------------
# Missing key
# ---------------------------------------------------------------------------


class TestMissingKey:

    def test_encrypt_without_key_raises(self):
        with patch("app.core.encryption.settings", _make_settings("")):
            with pytest.raises(ValueError, match="ENCRYPTION_KEY must be set"):
                enc.encrypt_token("test")

    def test_decrypt_without_key_raises(self):
        """Decrypting with no key set raises ValueError (either missing key or corrupt data)."""
        with patch("app.core.encryption.settings", _make_settings("")):
            with pytest.raises(ValueError):
                enc.decrypt_token("v1:dGVzdA==")


# ---------------------------------------------------------------------------
# Key isolation (different keys produce different ciphertexts)
# ---------------------------------------------------------------------------


class TestKeyIsolation:

    def test_different_keys_cannot_cross_decrypt(self):
        with patch("app.core.encryption.settings", _make_settings("key-alpha")):
            ct = enc.encrypt_token("isolated")
        enc.reset_cache()
        with patch("app.core.encryption.settings", _make_settings("key-beta")):
            with pytest.raises(ValueError):
                enc.decrypt_token(ct)
