"""Role-based access control (RBAC) tests.

Covers the role → permission matrix, Clerk-claim role resolution, the
``require_permission`` dependency (deny + audit), and the ``/v1/me`` endpoint.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import roles
from app.api.auth import Principal
from app.api.deps import require_permission


# --------------------------------------------------------------------------- #
# Permission matrix                                                            #
# --------------------------------------------------------------------------- #
def test_role_permission_matrix():
    # Admin and manager can approve; clerk and procurement cannot.
    assert roles.can(roles.ADMIN, roles.RUN_APPROVE)
    assert roles.can(roles.MANAGER, roles.RUN_APPROVE)
    assert not roles.can(roles.CLERK, roles.RUN_APPROVE)
    assert not roles.can(roles.PROCUREMENT, roles.RUN_APPROVE)

    # Auditor is strictly read-only — no mutation of any kind.
    assert roles.permissions_for(roles.AUDITOR) == [roles.RUN_READ]
    for perm in (roles.RUN_CREATE, roles.DRAFT_EDIT, roles.COMMS_SEND, roles.RUN_APPROVE):
        assert not roles.can(roles.AUDITOR, perm)

    # Every role can read.
    for role in roles.ALL_ROLES:
        assert roles.can(role, roles.RUN_READ)

    # An unknown role is granted nothing.
    assert roles.permissions_for("not-a-role") == []
    assert not roles.can(None, roles.RUN_READ)


# --------------------------------------------------------------------------- #
# Claim → role resolution                                                      #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "claims,expected",
    [
        ({"org_role": "org:admin"}, roles.ADMIN),                      # Clerk org admin
        ({"org_role": "org:member"}, roles.CLERK),                     # plain member → default
        ({"org_role": "org:controller"}, roles.CONTROLLER),            # custom org role
        ({"role": "ap_manager"}, roles.MANAGER),                       # explicit claim + alias
        ({"public_metadata": {"role": "Finance Controller"}}, roles.CONTROLLER),
        ({"ap_role": "auditor"}, roles.AUDITOR),
        ({}, roles.CLERK),                                             # nothing → configured default
    ],
)
def test_role_from_claims(claims, expected):
    assert roles.role_from_claims(claims, default_role=roles.CLERK) == expected


def test_role_from_claims_explicit_beats_org_role():
    # An explicit application-role claim wins over the org role.
    claims = {"org_role": "org:admin", "role": "auditor"}
    assert roles.role_from_claims(claims, default_role=roles.CLERK) == roles.AUDITOR


def test_role_from_claims_invalid_default_collapses_to_clerk():
    assert roles.role_from_claims({}, default_role="bogus") == roles.CLERK


# --------------------------------------------------------------------------- #
# require_permission dependency: deny + audit                                  #
# --------------------------------------------------------------------------- #
def _request(method: str, path: str, **path_params) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "scheme": "http",
        "server": ("testserver", 80),
        "path_params": path_params,
    }
    return Request(scope)


@pytest.fixture
def memory_store(monkeypatch):
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_KEY", "")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    from app.api import store as store_mod
    from app.config import get_settings

    get_settings.cache_clear()
    store_mod.reset_store_cache()
    yield store_mod.get_store()
    store_mod.reset_store_cache()
    get_settings.cache_clear()


def test_require_permission_allows_authorized_role(memory_store):
    dep = require_permission(roles.RUN_APPROVE)
    manager = Principal(subject="u-mgr", tenant_id="t1", role=roles.MANAGER, claims={})
    req = _request("POST", "/v1/runs/run_x/approve", run_id="run_x")
    # Returns the principal unchanged — no exception.
    assert dep(request=req, principal=manager) is manager


def test_require_permission_denies_and_audits(memory_store):
    from app.schemas import AuditEventType

    rid = "run_denied"
    memory_store.put(
        {
            "run_id": rid,
            "tenant_id": "t1",
            "status": "AWAITING_REVIEW",
            "created_at": "2026-01-01T00:00:00Z",
            "audit_events": [],
        }
    )

    dep = require_permission(roles.RUN_APPROVE)
    auditor = Principal(subject="u-aud", tenant_id="t1", role=roles.AUDITOR, claims={})
    req = _request("POST", f"/v1/runs/{rid}/approve", run_id=rid)

    with pytest.raises(HTTPException) as ei:
        dep(request=req, principal=auditor)
    assert ei.value.status_code == 403

    # The denial was recorded on the run's append-only audit trail.
    events = memory_store.get(rid).get("audit_events", [])
    denied = [e for e in events if e.event_type == AuditEventType.ACCESS_DENIED]
    assert len(denied) == 1
    assert denied[0].actor == "u-aud"
    assert denied[0].metadata["role"] == roles.AUDITOR
    assert denied[0].metadata["permission"] == roles.RUN_APPROVE


# --------------------------------------------------------------------------- #
# /v1/me                                                                       #
# --------------------------------------------------------------------------- #
def test_me_endpoint_auth_disabled_is_admin(monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    from app.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from app.api.main import app

    body = TestClient(app).get("/v1/me").json()
    assert body["role"] == roles.ADMIN
    assert set(body["permissions"]) == set(roles.ALL_PERMISSIONS)
    get_settings.cache_clear()
