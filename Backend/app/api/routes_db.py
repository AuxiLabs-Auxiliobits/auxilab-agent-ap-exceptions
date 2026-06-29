"""Read APIs over the normalized enterprise schema.

Available only when DB_PERSISTENCE_ENABLED=true. Demonstrates the normalized
model end-to-end: exception listing + dashboard aggregations sourced from the
relational tables (not the run-state blob).

Every endpoint is scoped to the caller's tenant: the tenant id comes from the
authenticated principal, never from a client-supplied parameter, so one org can
never read another org's invoices or dashboard.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import Principal
from app.api.deps import require_permission
from app.api.roles import RUN_READ
from app.config import get_settings
from app.db.repositories import DashboardRepository, ExceptionRepository
from app.db.session import session_scope
from app.schemas.db import ExceptionRecord

router = APIRouter(prefix="/v1/db", tags=["normalized-db"])


def _require_enabled() -> None:
    if not get_settings().db_persistence_enabled:
        raise HTTPException(
            503, "Normalized DB persistence is disabled (set DB_PERSISTENCE_ENABLED=true)."
        )


@router.get("/exceptions")
def list_exceptions(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_permission(RUN_READ)),
) -> dict:
    _require_enabled()
    with session_scope() as s:
        repo = ExceptionRepository(s)
        rows = repo.list(
            tenant_id=principal.tenant_id, status=status, limit=limit, offset=offset
        )
        total = repo.count(tenant_id=principal.tenant_id)
        return {
            "total": total,
            "count": len(rows),
            "exceptions": [ExceptionRecord.model_validate(r).model_dump(mode="json") for r in rows],
        }


@router.get("/dashboard")
def dashboard(principal: Principal = Depends(require_permission(RUN_READ))) -> dict:
    _require_enabled()
    with session_scope() as s:
        repo = DashboardRepository(s)
        metrics = repo.metrics(tenant_id=principal.tenant_id)
        metrics["top_5_priority"] = repo.top_priority(tenant_id=principal.tenant_id, n=5)
        return metrics
