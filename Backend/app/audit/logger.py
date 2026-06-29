"""Append-only audit event logging helpers."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.schemas import AuditEvent, AuditEventType


def hash_payload(payload: Any) -> str:
    if payload is None:
        return ""
    try:
        s = json.dumps(payload, sort_keys=True, default=str)
    except TypeError:
        s = str(payload)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def make_event(
    *,
    run_id: str,
    node_name: str,
    event_type: AuditEventType,
    invoice_id: str | None = None,
    input_payload: Any = None,
    output_payload: Any = None,
    actor: str = "system",
    metadata: dict | None = None,
) -> AuditEvent:
    return AuditEvent(
        event_id=str(uuid.uuid4()),
        run_id=run_id,
        invoice_id=invoice_id,
        node_name=node_name,
        event_type=event_type,
        timestamp=datetime.now(UTC),
        actor=actor,
        input_hash=hash_payload(input_payload) or None,
        output_hash=hash_payload(output_payload) or None,
        metadata=metadata or {},
    )
