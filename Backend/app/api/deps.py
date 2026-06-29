"""Shared FastAPI dependencies for route-level authorization."""
from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request

from app.api.auth import Principal, require_auth
from app.api.store import get_store

log = logging.getLogger("ap_agent.authz")


def get_owned_run(run_id: str, principal: Principal = Depends(require_auth)):
    """Fetch a run and enforce access.

    Returns the run state if it exists and the caller may access it: the run is
    in the caller's tenant (org) OR the caller uploaded it (owner). Scoping by
    uploader too lets a user open their own runs from any browser/org context.
    Raises 404 if missing, 403 otherwise. When auth is disabled (dev/tests) the
    principal is the local "dev" user and the check is skipped.
    """
    state = get_store().get(run_id)
    if state is None:
        raise HTTPException(404, "run not found")
    if principal.subject != "dev" and not (
        state.get("tenant_id") == principal.tenant_id
        or state.get("owner") == principal.subject
    ):
        raise HTTPException(403, "not authorized for this run")
    return state


def _audit_denied(request: Request, principal: Principal, permission: str) -> None:
    """Record a permission denial — always to the log, and to the run's
    append-only audit trail when the denied action is run-scoped, so an auditor
    can see who was refused what. Never raises (best-effort, on the 403 path)."""
    run_id = request.path_params.get("run_id")
    log.warning(
        "authz: denied subject=%s role=%s permission=%s method=%s path=%s run=%s",
        principal.subject,
        principal.role,
        permission,
        request.method,
        request.url.path,
        run_id,
    )
    if not run_id:
        return
    try:
        from app.audit.logger import make_event
        from app.schemas import AuditEventType

        store = get_store()
        state = store.get(run_id)
        if state is None:
            return
        state.setdefault("audit_events", []).append(
            make_event(
                run_id=run_id,
                invoice_id=request.path_params.get("invoice_id"),
                node_name="authz",
                event_type=AuditEventType.ACCESS_DENIED,
                actor=principal.subject or "unknown",
                metadata={
                    "role": principal.role,
                    "permission": permission,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
        )
        store.put(state)
    except Exception:  # noqa: BLE001 — auditing a denial must never mask the 403
        log.exception("authz: failed to record access-denied audit event")


def require_permission(permission: str) -> Callable[..., Principal]:
    """Build a FastAPI dependency that requires ``permission`` on the caller.

    Returns the :class:`Principal` (so the route can stamp the actor on its
    audit event). A denial logs, audits, and raises 403. With auth disabled the
    principal is the ``admin`` dev user, so every permission passes.
    """

    def _dep(request: Request, principal: Principal = Depends(require_auth)) -> Principal:
        if principal.has(permission):
            return principal
        _audit_denied(request, principal, permission)
        raise HTTPException(
            403,
            f"role '{principal.role}' is not permitted to '{permission}'",
        )

    return _dep
