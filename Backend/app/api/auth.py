"""Clerk JWT authentication for the API.

When AUTH_ENABLED=true, every /v1/* route requires a valid Clerk session token
in `Authorization: Bearer <token>`. The token (RS256) is verified against
Clerk's JWKS (signature + issuer + expiry, optional audience). JWKS keys are
fetched and cached by PyJWKClient.

When AUTH_ENABLED=false (dev/tests) the dependency is a no-op and returns a
local principal — so existing flows keep working until you flip the switch.
"""
from __future__ import annotations

import logging

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.api.roles import ADMIN, can, permissions_for, role_from_claims
from app.config import Settings, get_settings

log = logging.getLogger("ap_agent.auth")

# Auto-error off so we can return our own 401 (and allow the no-auth dev path).
_bearer = HTTPBearer(auto_error=False)

_jwks_client: PyJWKClient | None = None
_jwks_url_cached: str | None = None


class Principal:
    """The authenticated caller.

    ``tenant_id`` powers per-tenant scoping; ``role`` powers RBAC (see
    ``app.api.roles``). When auth is disabled (dev/tests) the principal is the
    local ``dev`` user with the ``admin`` role, so every existing flow keeps
    working until auth is switched on.
    """

    __slots__ = ("subject", "tenant_id", "role", "claims")

    def __init__(self, subject: str, tenant_id: str, role: str, claims: dict) -> None:
        self.subject = subject
        self.tenant_id = tenant_id
        self.role = role
        self.claims = claims

    def has(self, permission: str) -> bool:
        """True if this principal's role grants ``permission``."""
        return can(self.role, permission)

    @property
    def permissions(self) -> list[str]:
        return permissions_for(self.role)

    def __repr__(self) -> str:
        return (
            f"Principal(sub={self.subject!r}, tenant={self.tenant_id!r}, "
            f"role={self.role!r})"
        )


def _get_jwks_client(settings: Settings) -> PyJWKClient:
    global _jwks_client, _jwks_url_cached
    url = settings.jwks_url
    if not url:
        raise HTTPException(500, "AUTH_ENABLED but CLERK_ISSUER/JWKS URL not configured")
    if _jwks_client is None or _jwks_url_cached != url:
        _jwks_client = PyJWKClient(url, cache_keys=True)
        _jwks_url_cached = url
    return _jwks_client


def _tenant_from_claims(claims: dict) -> str:
    # Clerk org id is the natural tenant; fall back to a custom claim or subject.
    return (
        claims.get("org_id")
        or claims.get("tenant_id")
        or (claims.get("o") or {}).get("id")
        or claims.get("sub")
        or "default"
    )


def require_auth(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """FastAPI dependency. Verifies the Clerk JWT when auth is enabled."""
    if not settings.auth_enabled:
        return Principal(subject="dev", tenant_id="default", role=ADMIN, claims={})

    if creds is None or not creds.credentials:
        raise HTTPException(401, "Missing bearer token")

    token = creds.credentials
    try:
        signing_key = _get_jwks_client(settings).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer or None,
            audience=settings.clerk_audience or None,
            options={
                "verify_aud": bool(settings.clerk_audience),
                "verify_iss": bool(settings.clerk_issuer),
            },
        )
    except HTTPException:
        raise
    except jwt.PyJWTError as e:
        log.info("auth: token rejected: %s", e)
        raise HTTPException(401, f"Invalid token: {e}") from e
    except Exception as e:  # JWKS fetch / network
        log.warning("auth: verification error: %s", e)
        raise HTTPException(401, "Token verification failed") from e

    principal = Principal(
        subject=str(claims.get("sub", "")),
        tenant_id=str(_tenant_from_claims(claims)),
        role=role_from_claims(claims, settings.auth_default_role),
        claims=claims,
    )
    request.state.principal = principal
    return principal
