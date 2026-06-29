"""LangGraph RunState definition."""
from __future__ import annotations

from datetime import datetime
from typing import TypedDict

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


class RunState(TypedDict, total=False):
    # Identity
    run_id: str
    tenant_id: str
    # The user (Clerk subject) who created the run. Lets a user see their own
    # uploads from any browser/org context, in addition to their tenant's runs.
    owner: str
    created_at: datetime
    source_file_hash: str
    source_filename: str

    # Per-stage payloads
    rows: list[ExceptionRow]
    quarantined: list[QuarantinedRow]
    classifications: list[ClassificationResult]
    resolutions: list[ResolutionDecision]
    drafts: list[CommunicationDraft]
    priority_queues: PriorityQueues
    metrics: DashboardMetrics

    # Bookkeeping
    errors: list[NodeError]
    audit_events: list[AuditEvent]
    status: RunStatus
    current_node: str

    # Human resolution lifecycle, set post-run via the review API:
    # invoice_id -> Case dict (status / note / updated_at / updated_by).
    cases: dict

    # Transient ingest input — set by the API layer, stripped by ingest_node.
    # Declared here so LangGraph propagates them through the StateGraph
    # (TypedDict keys not declared are dropped).
    _input_bytes: bytes
    _input_filename: str
    completed_at: datetime
