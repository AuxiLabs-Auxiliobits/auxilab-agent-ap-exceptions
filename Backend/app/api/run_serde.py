"""Shared (de)serialization for run-store backends.

A RunState is a dict of Pydantic models, datetimes and enums. Both durable
run stores — the SQLAlchemy/Postgres store (db_store.py) and the Supabase REST
store (supabase_store.py) — persist it as one JSON blob plus a few indexed
scalar columns. Keeping the conversion here means the two backends serialize
identically and a run written by one is readable by the other.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from app.graph.state import RunState
from app.schemas import (
    AuditEvent,
    ClassificationResult,
    CommunicationDraft,
    DashboardMetrics,
    ExceptionRow,
    NodeError,
    PriorityQueues,
    QuarantinedRow,
    ResolutionDecision,
    RunStatus,
)

# state key -> Pydantic model class (lists of models)
_LIST_MODELS = {
    "rows": ExceptionRow,
    "quarantined": QuarantinedRow,
    "classifications": ClassificationResult,
    "resolutions": ResolutionDecision,
    "drafts": CommunicationDraft,
    "errors": NodeError,
    "audit_events": AuditEvent,
}
# state key -> Pydantic model class (single model)
_SINGLE_MODELS = {
    "priority_queues": PriorityQueues,
    "metrics": DashboardMetrics,
}
_DATETIME_KEYS = ("created_at", "completed_at")


def serialize_state(state: RunState) -> dict[str, Any]:
    """RunState (Pydantic models + datetimes + enums) -> JSON-safe dict.

    Transient keys (leading underscore, e.g. raw input bytes) are dropped.
    """
    out: dict[str, Any] = {}
    for k, v in state.items():
        if k.startswith("_"):
            continue
        if isinstance(v, list) and v and hasattr(v[0], "model_dump"):
            out[k] = [item.model_dump(mode="json") for item in v]
        elif hasattr(v, "model_dump"):
            out[k] = v.model_dump(mode="json")
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, Enum):
            out[k] = v.value
        else:
            out[k] = v
    return out


def deserialize_state(raw: dict[str, Any]) -> RunState:
    """JSON dict -> RunState with Pydantic models / datetimes / enums restored."""
    state: dict[str, Any] = dict(raw)
    for key, cls in _LIST_MODELS.items():
        if isinstance(state.get(key), list):
            state[key] = [cls.model_validate(x) for x in state[key]]
    for key, cls in _SINGLE_MODELS.items():
        if isinstance(state.get(key), dict):
            state[key] = cls.model_validate(state[key])
    if isinstance(state.get("status"), str):
        state["status"] = RunStatus(state["status"])
    for key in _DATETIME_KEYS:
        if isinstance(state.get(key), str):
            try:
                state[key] = datetime.fromisoformat(state[key])
            except ValueError:
                pass
    return state  # type: ignore[return-value]


def scalar_columns(state: RunState) -> dict[str, Any]:
    """The indexed scalar columns mirrored out of the state for listing/filtering."""
    status = state.get("status")
    created = state.get("created_at")
    completed = state.get("completed_at")
    return {
        "run_id": state["run_id"],
        "tenant_id": state.get("tenant_id"),
        "status": status.value if isinstance(status, Enum) else status,
        "current_node": state.get("current_node"),
        "created_at": created.isoformat() if isinstance(created, datetime) else created,
        "completed_at": completed.isoformat() if isinstance(completed, datetime) else completed,
        "rows_accepted": len(state.get("rows", [])),
        "rows_quarantined": len(state.get("quarantined", [])),
    }
