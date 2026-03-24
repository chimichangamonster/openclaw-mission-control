"""WeCom message signature verification and AES encrypt/decrypt.

WeCom uses a custom AES-CBC-256 scheme for message encryption:
- Key: Base64-decoded from the 43-char EncodingAESKey + "=" padding
- IV: First 16 bytes of the AES key
- Plaintext layout: 16-byte random prefix + 4-byte msg length (big-endian) + msg + corp_id
- PKCS#7 padding (block size 32, not the standard 16)
"""

from __future__ import annotations

import base64
import hashlib
import os
import struct
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WeComCryptoError(Exception):
    """Raised when WeCom message encryption/decryption fails."""


def verify_signature(
    token: str,
    timestamp: str,
    nonce: str,
    *,
    msg_encrypt: str = "",
    signature: str,
) -> None:
    """Verify the SHA1 signature from WeCom's callback request.

    Raises WeComCryptoError if the signature does not match.
    """
    parts = sorted([token, timestamp, nonce, msg_encrypt])
    computed = hashlib.sha1("".join(parts).encode()).hexdigest()
    if computed != signature:
        raise WeComCryptoError("Signature verification failed")


def check_timestamp(timestamp: str, *, max_age_seconds: int = 300) -> None:
    """Reject timestamps older than max_age_seconds (replay protection)."""
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        raise WeComCryptoError("Invalid timestamp")
    if abs(time.time() - ts) > max_age_seconds:
        raise WeComCryptoError("Timestamp too old — possible replay attack")


def _decode_aes_key(encoding_aes_key: str) -> bytes:
    """Decode the 43-char EncodingAESKey to a 32-byte AES key."""
    return base64.b64decode(encoding_aes_key + "=")


def _pkcs7_pad(data: bytes, block_size: int = 32) -> bytes:
    """PKCS#7 padding with WeCom's non-standard block size of 32."""
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    """Remove PKCS#7 padding."""
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 32:
        raise WeComCryptoError("Invalid PKCS#7 padding")
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        raise WeComCryptoError("Invalid PKCS#7 padding")
    return data[:-pad_len]


def decrypt_message(encoding_aes_key: str, encrypted_msg: str, corp_id: str) -> str:
    """Decrypt a WeCom encrypted message and verify corp_id.

    Returns the decrypted message text.
    """
    aes_key = _decode_aes_key(encoding_aes_key)
    iv = aes_key[:16]

    ciphertext = base64.b64decode(encrypted_msg)
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    plaintext = _pkcs7_unpad(decryptor.update(ciphertext) + decryptor.finalize())

    # Layout: 16-byte random + 4-byte msg_length (big-endian) + msg + corp_id
    msg_length = struct.unpack(">I", plaintext[16:20])[0]
    msg = plaintext[20 : 20 + msg_length].decode("utf-8")
    extracted_corp_id = plaintext[20 + msg_length :].decode("utf-8")

    if extracted_corp_id != corp_id:
        raise WeComCryptoError(
            f"Corp ID mismatch: expected {corp_id}, got {extracted_corp_id}"
        )

    return msg


def encrypt_message(encoding_aes_key: str, corp_id: str, plaintext_msg: str) -> str:
    """Encrypt a reply message using WeCom's AES scheme.

    Returns the Base64-encoded ciphertext.
    """
    aes_key = _decode_aes_key(encoding_aes_key)
    iv = aes_key[:16]

    msg_bytes = plaintext_msg.encode("utf-8")
    corp_bytes = corp_id.encode("utf-8")
    random_prefix = os.urandom(16)
    msg_length = struct.pack(">I", len(msg_bytes))

    raw = random_prefix + msg_length + msg_bytes + corp_bytes
    padded = _pkcs7_pad(raw)

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    return base64.b64encode(ciphertext).decode("utf-8")
