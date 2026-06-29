"""Audit event schema."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AuditEventType(str, Enum):
    NODE_START = "NODE_START"
    NODE_END = "NODE_END"
    AI_CALL = "AI_CALL"
    RULE_FIRE = "RULE_FIRE"
    RULE_OVERRIDE = "RULE_OVERRIDE"  # a human changed the agent's resolution path
    HUMAN_EDIT = "HUMAN_EDIT"
    CASE_UPDATE = "CASE_UPDATE"  # a human advanced an exception's resolution lifecycle
    APPROVAL = "APPROVAL"
    ERROR = "ERROR"
    INGEST_QUARANTINE = "INGEST_QUARANTINE"
    ACCESS_DENIED = "ACCESS_DENIED"


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    run_id: str
    invoice_id: str | None = None
    node_name: str
    event_type: AuditEventType
    timestamp: datetime
    actor: str = "system"
    input_hash: str | None = None
    output_hash: str | None = None
    metadata: dict = Field(default_factory=dict)
