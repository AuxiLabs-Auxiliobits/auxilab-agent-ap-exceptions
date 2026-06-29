"""Symmetric encryption for per-org integration secrets.

Secrets (BYOK API keys, etc.) are stored encrypted at rest. We use Fernet
(AES-128-CBC + HMAC-SHA256, from `cryptography`) keyed by ``CONFIG_ENC_KEY``.

Generate a key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

The key lives in the backend environment (or a KMS/secret manager that
populates it). Without it, the app refuses to encrypt/decrypt rather than
storing plaintext — fail safe, never fail open.
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretCryptoError(RuntimeError):
    """Raised when encryption/decryption can't proceed (missing/invalid key)."""


def is_configured() -> bool:
    """True if a usable CONFIG_ENC_KEY is set."""
    return bool(get_settings().config_enc_key)


def _fernet() -> Fernet:
    key = get_settings().config_enc_key
    if not key:
        raise SecretCryptoError(
            "CONFIG_ENC_KEY is not set — cannot store or read per-org integration "
            "secrets. Generate one with "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())".'
        )
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception as e:  # malformed key
        raise SecretCryptoError(
            "CONFIG_ENC_KEY is invalid — it must be a urlsafe-base64 32-byte "
            f"Fernet key. ({e})"
        ) from e


def encrypt(plaintext: str) -> bytes:
    """Encrypt a UTF-8 secret. Returns the ciphertext token (bytes)."""
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt(token: bytes | str) -> str:
    """Decrypt a ciphertext token back to the UTF-8 secret."""
    if isinstance(token, str):
        token = token.encode("utf-8")
    try:
        return _fernet().decrypt(token).decode("utf-8")
    except InvalidToken as e:
        raise SecretCryptoError(
            "Could not decrypt a stored secret (wrong CONFIG_ENC_KEY or corrupted "
            "data). If the key was rotated, the secret must be re-entered."
        ) from e
