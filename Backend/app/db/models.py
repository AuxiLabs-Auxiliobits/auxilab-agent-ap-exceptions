"""SQLAlchemy 2.0 ORM models for the normalized AP-exception schema.

Portable types (Uuid, JSON, Numeric, String) so `Base.metadata.create_all`
works identically on SQLite (dev) and PostgreSQL/Supabase (prod). Enum-valued
columns are stored as String and validated upstream by the pipeline's Pydantic
models; a production deploy can tighten them to native PG enums.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# JSON on SQLite (dev), JSONB on PostgreSQL/Supabase (prod) — keeps create_all
# portable while giving the operational run-store column proper jsonb semantics
# (indexing/containment) and matching supabase/schema.sql.
_JSONB = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    file_name: Mapped[str] = mapped_column(String(512))
    source_file_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    processed_records: Mapped[int] = mapped_column(Integer, default=0)
    failed_records: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="Uploaded")
    uploaded_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    upload_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    exceptions: Mapped[list[ExceptionRecord]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("tenant_id", "vendor_name", name="uq_vendor_tenant_name"),)

    vendor_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    vendor_name: Mapped[str] = mapped_column(String(256), index=True)
    total_invoices_seen: Mapped[int] = mapped_column(Integer, default=0)
    total_amount_processed: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    reliability_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    exception_type_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    # Full VendorProfile snapshot (rolling averages + per-type/path counts) so
    # the DB-backed vendor store is a lossless drop-in for the JSON file store.
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExceptionRecord(Base):
    __tablename__ = "exceptions"
    __table_args__ = (UniqueConstraint("batch_id", "invoice_id", name="uq_exc_batch_invoice"),)

    exception_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("upload_batches.batch_id", ondelete="CASCADE"), index=True)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.vendor_id", ondelete="SET NULL"), nullable=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    invoice_id: Mapped[str] = mapped_column(String(64), index=True)
    vendor_name: Mapped[str] = mapped_column(String(256))
    invoice_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    po_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    exception_type: Mapped[str] = mapped_column(String(64))
    exception_description: Mapped[str] = mapped_column(Text)
    days_outstanding: Mapped[int] = mapped_column(Integer)
    approver_assigned: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    upload_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    current_status: Mapped[str] = mapped_column(String(32), default="New", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    batch: Mapped[UploadBatch] = relationship(back_populates="exceptions")
    classification: Mapped[Classification | None] = relationship(back_populates="exception", cascade="all, delete-orphan", uselist=False)
    resolution: Mapped[Resolution | None] = relationship(back_populates="exception", cascade="all, delete-orphan", uselist=False)
    priority: Mapped[Priority | None] = relationship(back_populates="exception", cascade="all, delete-orphan", uselist=False)
    communications: Mapped[list[Communication]] = relationship(back_populates="exception", cascade="all, delete-orphan")
    history: Mapped[list[StatusHistory]] = relationship(back_populates="exception", cascade="all, delete-orphan")


class Classification(Base):
    __tablename__ = "classifications"

    classification_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    exception_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exceptions.exception_id", ondelete="CASCADE"), index=True)
    primary_exception_type: Mapped[str] = mapped_column(String(64))
    root_cause_hypothesis: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(Numeric(4, 3))
    severity: Mapped[str] = mapped_column(String(16))
    severity_ai_suggested: Mapped[str] = mapped_column(String(16))
    ai_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    classified_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exception: Mapped[ExceptionRecord] = relationship(back_populates="classification")


class Resolution(Base):
    __tablename__ = "resolutions"

    resolution_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    exception_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exceptions.exception_id", ondelete="CASCADE"), index=True)
    resolution_path: Mapped[str] = mapped_column(String(48))
    assigned_team: Mapped[str | None] = mapped_column(String(128), nullable=True)
    assigned_user: Mapped[str | None] = mapped_column(String(256), nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(32), default="Classified", index=True)
    rule_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rule_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sla_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requires_communication: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    exception: Mapped[ExceptionRecord] = relationship(back_populates="resolution")


class Communication(Base):
    __tablename__ = "communications"

    email_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    exception_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exceptions.exception_id", ondelete="CASCADE"), index=True)
    email_type: Mapped[str] = mapped_column(String(32))
    channel: Mapped[str] = mapped_column(String(32))
    recipient_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    cc_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    email_body: Mapped[str] = mapped_column(Text)
    template_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generated_by_ai: Mapped[bool] = mapped_column(Boolean, default=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sent_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(16), default="Draft", index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exception: Mapped[ExceptionRecord] = relationship(back_populates="communications")


class StatusHistory(Base):
    __tablename__ = "status_history"

    history_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    exception_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exceptions.exception_id", ondelete="CASCADE"), index=True)
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32))
    changed_by: Mapped[str] = mapped_column(String(256), default="system")
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exception: Mapped[ExceptionRecord] = relationship(back_populates="history")


class AgentExecution(Base):
    __tablename__ = "agent_executions"

    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("upload_batches.batch_id", ondelete="CASCADE"), nullable=True, index=True)
    exception_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("exceptions.exception_id", ondelete="CASCADE"), nullable=True, index=True)
    node_name: Mapped[str] = mapped_column(String(64))
    node_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    node_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    success_flag: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Priority(Base):
    __tablename__ = "priorities"

    priority_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    exception_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exceptions.exception_id", ondelete="CASCADE"), unique=True, index=True)
    priority_score: Mapped[float] = mapped_column(Numeric(5, 4))
    priority_bucket: Mapped[str] = mapped_column(String(16), index=True)
    ranking_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    drivers: Mapped[list] = mapped_column(JSON, default=list)
    last_priority_update: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    exception: Mapped[ExceptionRecord] = relationship(back_populates="priority")


class Run(Base):
    """Operational run-store row: the full serialized RunState as one JSONB blob
    plus indexed scalar columns for listing/filtering. This is what the API
    reads/writes on every pipeline step (see app/api/db_store.py) — distinct
    from the normalized analytical tables above, and the DB-backed replacement
    for the in-memory / Supabase-REST run stores."""

    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_accepted: Mapped[int] = mapped_column(Integer, default=0)
    rows_quarantined: Mapped[int] = mapped_column(Integer, default=0)
    state: Mapped[dict] = mapped_column(_JSONB, nullable=False)


class RunJob(Base):
    """Durable run-execution queue row (see app/api/job_queue.py).

    Decouples "a run was submitted" from "a run finished executing": the
    uploaded input is persisted (gzipped) so a worker can execute — or re-execute
    after a crash — without the original HTTP request. Survives restarts, leases
    work to a single worker at a time, and reclaims jobs whose worker died."""

    __tablename__ = "run_jobs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    filename: Mapped[str] = mapped_column(String(512))
    input_gz: Mapped[bytes] = mapped_column(LargeBinary)
    # queued -> running -> done | failed
    queue_status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    leased_by: Mapped[str | None] = mapped_column(String(96), nullable=True)
    leased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Earliest time this job may be claimed again. Set into the future on a
    # failed attempt (retry backoff); NULL = claimable immediately.
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class OrgIntegration(Base):
    """Per-organization (tenant) integration config — BYOK provider credentials.

    One row per (tenant_id, kind). The secret (e.g. an API key) is stored
    ENCRYPTED in ``secret_ciphertext`` (see app/security/crypto.py); non-secret
    settings (model ids, endpoint, sender) live in ``meta`` for display. Secrets
    are never returned by the API.
    """

    __tablename__ = "org_integrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "kind", name="uq_org_integration_tenant_kind"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    # ai_anthropic | ai_gemini | ai_azure | email | slack
    kind: Mapped[str] = mapped_column(String(32))
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Subscriber(Base):
    """Newsletter subscriber (platform-level marketing list, not per-tenant).

    Captured from the public landing page. Each row carries a stable
    ``unsubscribe_token`` used to build one-click unsubscribe links (CAN-SPAM /
    GDPR). ``status`` is 'active' or 'unsubscribed'.
    """

    __tablename__ = "subscribers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unsubscribe_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrgPolicy(Base):
    """Per-tenant resolution rulebook — overrides the global default policy.

    Each org can tune its own thresholds/routing; the route node resolves this
    when present and falls back to the platform default otherwise. The full
    validated policy document (``{version, rules:[...]}``) is stored as JSON.
    Non-secret config (not credentials), one row per tenant."""

    __tablename__ = "org_policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(64))
    policy: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Lead(Base):
    """Sales/support lead captured from the public Contact form (platform-level,
    not per-tenant).

    Persisted so a prospect is never lost if the notification email is missed or
    the inbox is unmonitored. ``intent`` tags the inquiry (demo / pricing /
    support / general) so sales vs support can be triaged, and ``status`` lets
    the operator mark a lead worked ('new' on capture)."""

    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    intent: Mapped[str] = mapped_column(String(32), default="general", index=True)
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VendorContact(Base):
    """Per-tenant vendor → email directory (F1-5).

    Recipient resolution looks a vendor's AR email up here, so a single upload
    mixing many vendors routes each invoice to the right vendor (and with bulk
    consolidation, each vendor gets one email for all their invoices). One row
    per (tenant_id, vendor_key) where vendor_key is the normalized vendor name."""

    __tablename__ = "vendor_contacts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "vendor_key", name="uq_vendor_contact_tenant_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), index=True)
    vendor_key: Mapped[str] = mapped_column(String(256), index=True)  # normalized (lower/stripped)
    vendor_name: Mapped[str] = mapped_column(String(256))             # display name
    email: Mapped[str] = mapped_column(String(320))
    contact_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CommsSendCounter(Base):
    """Per-(tenant, UTC day, recipient domain) live-send counter.

    Backs the distributed per-domain daily send cap (escalation-storm guard). A
    DB row + atomic conditional increment makes the cap hold across replicas,
    unlike the in-process counter. One row per (tenant_id, day_iso, domain)."""

    __tablename__ = "comms_send_counters"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    day_iso: Mapped[str] = mapped_column(String(10), primary_key=True)   # YYYY-MM-DD (UTC)
    domain: Mapped[str] = mapped_column(String(255), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
