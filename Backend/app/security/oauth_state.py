"""Signed, expiring OAuth `state` tokens (CSRF protection).

The OAuth `state` round-trips through the provider, so it must be tamper-proof.
We HMAC a small JSON payload (tenant + kind + issued-at) with a key derived from
CONFIG_ENC_KEY. ``verify`` rejects tampered or expired tokens.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.config import get_settings


class OAuthStateError(RuntimeError):
    """Raised when a state token is missing, tampered, or expired."""


def _key() -> bytes:
    secret = get_settings().config_enc_key
    if not secret:
        raise OAuthStateError("CONFIG_ENC_KEY is not set — cannot sign OAuth state.")
    # Derive a stable 32-byte HMAC key from the configured secret.
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(payload: dict) -> str:
    body = dict(payload)
    body["iat"] = int(time.time())
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    sig = hmac.new(_key(), raw, hashlib.sha256).digest()
    return f"{_b64e(raw)}.{_b64e(sig)}"


def verify(token: str, *, max_age_seconds: int = 600) -> dict:
    try:
        raw_b64, sig_b64 = token.split(".", 1)
        raw = _b64d(raw_b64)
        sig = _b64d(sig_b64)
    except Exception as e:  # noqa: BLE001
        raise OAuthStateError("malformed state token") from e
    expected = hmac.new(_key(), raw, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise OAuthStateError("state signature mismatch")
    body = json.loads(raw.decode("utf-8"))
    if int(time.time()) - int(body.get("iat", 0)) > max_age_seconds:
        raise OAuthStateError("state expired — restart the connection")
    return body
