"""Read-side repositories over the normalized schema.

Thin query helpers used by the DB-backed read APIs (routes_db.py). Writes go
through app/db/persistence.py.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import models as m


class ExceptionRepository:
    def __init__(self, session: Session) -> None:
        self.s = session

    def list(
        self,
        *,
        tenant_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[m.ExceptionRecord]:
        stmt = select(m.ExceptionRecord)
        if tenant_id:
            stmt = stmt.where(m.ExceptionRecord.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(m.ExceptionRecord.current_status == status)
        stmt = stmt.order_by(m.ExceptionRecord.created_at.desc()).limit(limit).offset(offset)
        return list(self.s.scalars(stmt))

    def count(self, *, tenant_id: str | None = None) -> int:
        stmt = select(func.count()).select_from(m.ExceptionRecord)
        if tenant_id:
            stmt = stmt.where(m.ExceptionRecord.tenant_id == tenant_id)
        return self.s.scalar(stmt) or 0


class DashboardRepository:
    """Aggregations for the dashboard (Total/Open/Resolved/Escalated/etc.)."""

    _OPEN = (
        "New", "Classified", "Pending Vendor", "Pending Requestor",
        "Pending Finance Review", "Escalated",
    )

    def __init__(self, session: Session) -> None:
        self.s = session

    def metrics(self, *, tenant_id: str | None = None) -> dict:
        exc = m.ExceptionRecord

        def _scoped(stmt):
            return stmt.where(exc.tenant_id == tenant_id) if tenant_id else stmt

        total = self.s.scalar(_scoped(select(func.count()).select_from(exc))) or 0
        total_value = self.s.scalar(_scoped(select(func.coalesce(func.sum(exc.invoice_amount), 0)))) or 0
        open_count = self.s.scalar(
            _scoped(select(func.count()).select_from(exc).where(exc.current_status.in_(self._OPEN)))
        ) or 0
        resolved = self.s.scalar(
            _scoped(select(func.count()).select_from(exc).where(exc.current_status.in_(("Resolved", "Closed"))))
        ) or 0
        escalated = self.s.scalar(
            _scoped(select(func.count()).select_from(exc).where(exc.current_status == "Escalated"))
        ) or 0
        auto = self.s.scalar(
            _scoped(select(func.count()).select_from(exc).where(exc.current_status == "Auto Approved"))
        ) or 0

        # breakdowns
        by_type = dict(
            self.s.execute(
                _scoped(select(exc.exception_type, func.count()).group_by(exc.exception_type))
            ).all()
        )
        by_vendor = dict(
            self.s.execute(
                _scoped(
                    select(exc.vendor_name, func.count())
                    .group_by(exc.vendor_name)
                    .order_by(func.count().desc())
                    .limit(10)
                )
            ).all()
        )

        return {
            "total_exceptions": total,
            "open_exceptions": open_count,
            "resolved_exceptions": resolved,
            "escalated_exceptions": escalated,
            "auto_approved_count": auto,
            "total_queue_value": float(total_value),
            "exception_type_breakdown": by_type,
            "vendor_breakdown": by_vendor,
        }

    def top_priority(self, *, tenant_id: str | None = None, n: int = 5) -> list[dict]:
        exc, pri = m.ExceptionRecord, m.Priority
        stmt = (
            select(exc.invoice_id, exc.vendor_name, exc.invoice_amount, pri.priority_score, pri.priority_bucket)
            .join(pri, pri.exception_id == exc.exception_id)
        )
        if tenant_id:
            stmt = stmt.where(exc.tenant_id == tenant_id)
        stmt = stmt.order_by(pri.priority_score.desc()).limit(n)
        return [
            {
                "invoice_id": r[0],
                "vendor_name": r[1],
                "invoice_amount": float(r[2]),
                "priority_score": float(r[3]),
                "priority_bucket": r[4],
            }
            for r in self.s.execute(stmt).all()
        ]
