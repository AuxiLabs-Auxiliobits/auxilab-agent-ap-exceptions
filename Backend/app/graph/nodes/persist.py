"""Persist node — writes final state snapshot to disk.

This is a minimal local-filesystem implementation. In a production
deployment this would write to Postgres + S3 (Object Lock for the audit
trail). The interface is identical so the production swap is a single
module change.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.audit.logger import make_event
from app.config import get_settings
from app.graph.state import RunState
from app.schemas import AuditEventType, RunStatus

log = logging.getLogger("ap_agent.persist")


def _to_jsonable(state: RunState) -> dict:
    """Serialize state, handling Pydantic models and enums."""
    out: dict = {}
    for k, v in state.items():
        if isinstance(v, list) and v and hasattr(v[0], "model_dump"):
            out[k] = [item.model_dump(mode="json") for item in v]
        elif hasattr(v, "model_dump"):
            out[k] = v.model_dump(mode="json")
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def persist_node(state: RunState) -> RunState:
    from app.graph._logging import step_log

    settings = get_settings()
    run_id = state["run_id"]
    artifacts = Path(settings.artifact_dir) / run_id
    artifacts.mkdir(parents=True, exist_ok=True)

    with step_log("persist_node", state) as info:
        snapshot = _to_jsonable(state)
        snapshot_path = artifacts / "run_state.json.gz"
        with gzip.open(snapshot_path, "wt", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, default=str)

        audit_path = artifacts / "audit.jsonl"
        with audit_path.open("a", encoding="utf-8") as f:
            for ev in state.get("audit_events", []):
                f.write(json.dumps(ev.model_dump(mode="json"), default=str) + "\n")

        snap_size = snapshot_path.stat().st_size
        log.info(
            "persist: wrote snapshot=%s size=%d audit_events=%d",
            snapshot_path,
            snap_size,
            len(state.get("audit_events", [])),
        )

        audit = list(state.get("audit_events", []))
        audit.append(
            make_event(
                run_id=run_id,
                node_name="persist_node",
                event_type=AuditEventType.NODE_END,
                metadata={"snapshot": str(snapshot_path)},
            )
        )

        info["snapshot"] = snapshot_path.name
        info["bytes"] = snap_size

    out = dict(state)
    out["audit_events"] = audit
    out["status"] = RunStatus.AWAITING_REVIEW
    out["current_node"] = "persist_node"

    # Normalized enterprise persistence (opt-in via DB_PERSISTENCE_ENABLED).
    # Writes the full audit-event list, so persist after appending NODE_END.
    # Self-guarded + never raises into the pipeline.
    from app.db.persistence import persist_run

    persist_run(out)
    return out


def utcnow():
    return datetime.now(UTC)
