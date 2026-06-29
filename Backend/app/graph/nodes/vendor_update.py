"""Vendor profile update node — deterministic.

Folds each row's classification + resolution into the vendor's longitudinal
profile, then flushes once to disk. Runs after prioritize_node and before
persist_node so updates are part of the same run snapshot.

This is intentionally a separate node (rather than inlined into persist)
so that:
  - the audit log carries a NODE_START/NODE_END for the learning step,
  - the node can be toggled off via `settings.vendor_history_enabled`
    without touching persistence,
  - future variants (learn-only-after-human-approval) become a one-line
    change here.
"""
from __future__ import annotations

import logging

from app.audit.logger import make_event
from app.config import get_settings
from app.graph.state import RunState
from app.schemas import AuditEventType

log = logging.getLogger("ap_agent.vendor_update")


def vendor_update_node(state: RunState) -> RunState:
    from app.graph._logging import step_log

    settings = get_settings()
    audit = list(state.get("audit_events", []))
    out = dict(state)
    out["current_node"] = "vendor_update_node"

    if not settings.vendor_history_enabled:
        log.info("vendor_update: disabled by settings; skipping")
        audit.append(
            make_event(
                run_id=state["run_id"],
                node_name="vendor_update_node",
                event_type=AuditEventType.NODE_END,
                metadata={"disabled": True},
            )
        )
        out["audit_events"] = audit
        return out

    with step_log("vendor_update_node", state) as info:
        from app.vendor import get_vendor_store

        rows = {r.invoice_id: r for r in state.get("rows", [])}
        classifications = {
            c.invoice_id: c for c in state.get("classifications", [])
        }
        resolutions = {r.invoice_id: r for r in state.get("resolutions", [])}

        store = get_vendor_store(settings)
        new_vendors = 0
        updates = 0
        for inv_id, row in rows.items():
            c = classifications.get(inv_id)
            r = resolutions.get(inv_id)
            if c is None or r is None:
                continue
            existed = store.get(row.vendor_name) is not None
            store.observe(row, c, r)
            updates += 1
            if not existed:
                new_vendors += 1

        store.flush()

        log.info(
            "vendor_update: observations=%d new_vendors=%d total_profiles=%d",
            updates,
            new_vendors,
            store.count(),
        )

        audit.append(
            make_event(
                run_id=state["run_id"],
                node_name="vendor_update_node",
                event_type=AuditEventType.NODE_END,
                metadata={
                    "observations": updates,
                    "new_vendors": new_vendors,
                    "total_profiles": store.count(),
                },
            )
        )

        info["observations"] = updates
        info["new_vendors"] = new_vendors

    out["audit_events"] = audit
    return out
