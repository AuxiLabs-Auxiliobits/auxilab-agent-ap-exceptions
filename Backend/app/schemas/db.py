"""DB-aligned Pydantic models for the normalized enterprise schema.

These mirror the SQLAlchemy ORM rows (app/db/models.py) and are what the read
APIs serialize. `from_attributes=True` lets them be built directly from ORM
instances.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExceptionStatus(str, Enum):
    NEW = "New"
    CLASSIFIED = "Classified"
    PENDING_VENDOR = "Pending Vendor"
    PENDING_REQUESTOR = "Pending Requestor"
    PENDING_FINANCE = "Pending Finance Review"
    AUTO_APPROVED = "Auto Approved"
    ESCALATED = "Escalated"
    RESOLVED = "Resolved"
    CLOSED = "Closed"


class BatchStatus(str, Enum):
    UPLOADED = "Uploaded"
    PROCESSING = "Processing"
    COMPLETED = "Completed"
    FAILED = "Failed"


class EmailType(str, Enum):
    VENDOR_QUERY = "Vendor Query"
    INTERNAL_REQUEST = "Internal Request"
    FINANCE_ESCALATION = "Finance Escalation"


class DeliveryStatus(str, Enum):
    DRAFT = "Draft"
    SENT = "Sent"
    DELIVERED = "Delivered"
    FAILED = "Failed"


class UploadBatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    batch_id: UUID
    tenant_id: str
    file_name: str
    source_file_hash: str | None = None
    total_records: int = 0
    processed_records: int = 0
    failed_records: int = 0
    status: str = BatchStatus.UPLOADED.value
    uploaded_by: str | None = None
    upload_time: datetime
    completed_at: datetime | None = None


class Vendor(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    vendor_id: UUID
    tenant_id: str
    vendor_name: str
    total_invoices_seen: int = 0
    total_amount_processed: Decimal = Decimal("0")
    reliability_score: float | None = None
    exception_type_counts: dict[str, int] = {}
    first_seen_at: datetime
    last_seen_at: datetime


class ExceptionRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    exception_id: UUID
    batch_id: UUID
    vendor_id: UUID | None = None
    tenant_id: str
    invoice_id: str
    vendor_name: str
    invoice_amount: Decimal = Field(ge=0)
    po_number: str | None = None
    exception_type: str
    exception_description: str
    days_outstanding: int = Field(ge=0)
    approver_assigned: str | None = None
    source_file_name: str | None = None
    uploaded_by: str | None = None
    upload_timestamp: datetime
    current_status: str = ExceptionStatus.NEW.value
    created_at: datetime
    updated_at: datetime


class Classification(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    classification_id: UUID
    exception_id: UUID
    primary_exception_type: str
    root_cause_hypothesis: str
    confidence_score: float = Field(ge=0, le=1)
    severity: str
    severity_ai_suggested: str
    ai_reasoning: str | None = None
    model_id: str | None = None
    prompt_version: str | None = None
    classified_timestamp: datetime


class Resolution(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    resolution_id: UUID
    exception_id: UUID
    resolution_path: str
    assigned_team: str | None = None
    assigned_user: str | None = None
    resolution_status: str = ExceptionStatus.CLASSIFIED.value
    rule_id: str | None = None
    rule_version: str | None = None
    sla_hours: int | None = None
    requires_communication: bool = False
    resolution_notes: str | None = None
    resolved_date: datetime | None = None
    closed_date: datetime | None = None
    created_at: datetime
    updated_at: datetime


class Communication(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    email_id: UUID
    exception_id: UUID
    email_type: str
    channel: str
    recipient_email: str | None = None
    cc_email: str | None = None
    subject: str | None = None
    email_body: str
    template_id: str | None = None
    generated_by_ai: bool = True
    model_id: str | None = None
    sent_flag: bool = False
    sent_timestamp: datetime | None = None
    delivery_status: str = DeliveryStatus.DRAFT.value
    provider: str | None = None
    message_id: str | None = None
    error_message: str | None = None
    created_at: datetime


class StatusHistory(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    history_id: UUID
    exception_id: UUID
    old_status: str | None = None
    new_status: str
    changed_by: str = "system"
    comments: str | None = None
    changed_timestamp: datetime


class AgentExecution(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    execution_id: UUID
    batch_id: UUID | None = None
    exception_id: UUID | None = None
    node_name: str
    node_input: dict | None = None
    node_output: dict | None = None
    success_flag: bool = True
    error_message: str | None = None
    duration_ms: int | None = None
    execution_timestamp: datetime


class Priority(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    priority_id: UUID
    exception_id: UUID
    priority_score: float = Field(ge=0, le=1)
    priority_bucket: str
    ranking_position: int | None = None
    drivers: list[str] = []
    last_priority_update: datetime
