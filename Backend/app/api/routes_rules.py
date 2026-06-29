"""Per-org resolution rulebook (admin-only).

Each org can tune its own routing rules; the route node uses the org's policy
when set and falls back to the platform default otherwise. Every endpoint is
gated on the admin-only ``config:write`` permission and scoped to the caller's
tenant. Saving validates the policy (structure + the mandatory catch-all rule),
so an unsafe rulebook can never be persisted.

  GET    /v1/org/rules            effective policy (custom or default) + is_custom
  PUT    /v1/org/rules            validate + store this org's policy
  DELETE /v1/org/rules            revert to the platform default
  POST   /v1/org/rules/validate   validate a candidate policy without saving
"""
from __future__ import annotations

import logging
from collections import Counter

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import ValidationError

from app.api import org_policy
from app.api.auth import Principal
from app.api.deps import require_permission
from app.api.roles import CONFIG_WRITE
from app.api.store import get_store
from app.config import get_settings
from app.rules.engine import RulesEngine, load_policy, to_decimal, validate_policy
from app.schemas import AuditEventType

log = logging.getLogger("ap_agent.routes_rules")

router = APIRouter(prefix="/v1/org/rules", tags=["rules"])


def _default_doc() -> dict:
    return load_policy(get_settings().rules_policy_path).model_dump(mode="json")


def _policy_from(body: dict) -> dict:
    """Accept either the raw policy document or a {"policy": {...}} envelope."""
    return body.get("policy", body) if isinstance(body, dict) else body


@router.get("")
def get_rules(principal: Principal = Depends(require_permission(CONFIG_WRITE))) -> dict:
    """The org's effective rulebook. ``is_custom`` is False when it uses the
    platform default; ``default_policy`` is always returned so the UI can show a
    'revert' baseline."""
    custom = org_policy.get_raw(principal.tenant_id)
    default_doc = _default_doc()
    return {
        "tenant_id": principal.tenant_id,
        "is_custom": custom is not None,
        "policy": custom if custom is not None else default_doc,
        "default_policy": default_doc,
    }


@router.put("")
def put_rules(
    body: dict = Body(...),
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    """Validate + store this org's rulebook. 422 if the policy is malformed or
    missing its catch-all rule."""
    try:
        policy = org_policy.upsert(
            principal.tenant_id, _policy_from(body), actor=principal.subject or "unknown"
        )
    except (ValidationError, ValueError) as e:
        raise HTTPException(422, f"invalid policy: {e}") from e
    log.info(
        "rules: policy set for tenant=%s version=%s rules=%d by=%s",
        principal.tenant_id, policy.version, len(policy.rules), principal.subject,
    )
    return {"tenant_id": principal.tenant_id, "is_custom": True, "version": policy.version}


@router.delete("")
def delete_rules(principal: Principal = Depends(require_permission(CONFIG_WRITE))) -> dict:
    """Drop the org's custom rulebook — routing reverts to the platform default."""
    had_custom = org_policy.delete(principal.tenant_id)
    return {"tenant_id": principal.tenant_id, "reverted_to_default": True, "had_custom": had_custom}


@router.post("/validate")
def validate_rules(
    body: dict = Body(...),
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    """Validate a candidate policy without saving — for the editor's live check."""
    try:
        policy = validate_policy(_policy_from(body))
    except (ValidationError, ValueError) as e:
        return {"ok": False, "error": str(e)[:1000]}
    return {"ok": True, "version": policy.version, "rules": len(policy.rules)}


@router.post("/simulate")
def simulate_rules(
    body: dict = Body(...),
    principal: Principal = Depends(require_permission(CONFIG_WRITE)),
) -> dict:
    """What-if: re-route a run under a candidate policy and diff against the org's
    *current* effective rulebook — so an admin sees the impact before saving.

    Both sides are evaluated now with the same auto-approve ceiling, so the diff
    reflects only the rule change. Body: ``{"run_id": ..., "policy": {...}}``.
    """
    run_id = body.get("run_id")
    if not run_id:
        raise HTTPException(400, "run_id is required")
    policy_doc = body.get("policy")
    if policy_doc is None:
        raise HTTPException(400, "policy is required")
    try:
        candidate_policy = validate_policy(policy_doc)
    except (ValidationError, ValueError) as e:
        raise HTTPException(422, f"invalid policy: {str(e)[:500]}") from None

    state = get_store().get(run_id)
    if state is None:
        raise HTTPException(404, "run not found")
    if principal.subject != "dev" and state.get("tenant_id") != principal.tenant_id:
        raise HTTPException(403, "not authorized for this run")

    # Baseline = the org's current effective policy (custom if set, else default).
    current_custom = None
    try:
        current_custom = org_policy.get_policy(state.get("tenant_id"))
    except Exception:  # noqa: BLE001 — fall back to default rather than 500
        current_custom = None
    current_policy = (
        current_custom if current_custom is not None else load_policy(get_settings().rules_policy_path)
    )
    current_engine = RulesEngine(current_policy)
    candidate_engine = RulesEngine(candidate_policy)

    s = get_settings()
    ceiling = (
        to_decimal(s.auto_approve_max_amount)
        if s.auto_approve_max_amount and s.auto_approve_max_amount > 0
        else None
    )

    rows = {r.invoice_id: r for r in state.get("rows", [])}
    cur_counter: Counter = Counter()
    sim_counter: Counter = Counter()
    changes: list[dict] = []
    for c in state.get("classifications", []):
        row = rows.get(c.invoice_id)
        if row is None:
            continue
        cur = current_engine.evaluate(row, c, auto_approve_ceiling=ceiling)
        sim = candidate_engine.evaluate(row, c, auto_approve_ceiling=ceiling)
        cur_counter[cur.resolution_path.value] += 1
        sim_counter[sim.resolution_path.value] += 1
        if cur.resolution_path != sim.resolution_path:
            changes.append(
                {
                    "invoice_id": row.invoice_id,
                    "vendor_name": row.vendor_name,
                    "invoice_amount": str(row.invoice_amount),
                    "exception_type": c.primary_exception_type.value,
                    "from": cur.resolution_path.value,
                    "to": sim.resolution_path.value,
                }
            )

    return {
        "run_id": run_id,
        "candidate_version": candidate_policy.version,
        "current_version": current_policy.version,
        "total": sum(cur_counter.values()),
        "changed_count": len(changes),
        "current_distribution": dict(cur_counter),
        "simulated_distribution": dict(sim_counter),
        "changes": changes,
    }


def _ev_type(ev) -> str | None:
    et = getattr(ev, "event_type", None)
    if et is not None:
        return et.value if hasattr(et, "value") else str(et)
    return ev.get("event_type") if isinstance(ev, dict) else None


def _ev_meta(ev) -> dict:
    md = getattr(ev, "metadata", None)
    if md is None and isinstance(ev, dict):
        md = ev.get("metadata")
    return md or {}


@router.get("/overrides")
def overrides_report(principal: Principal = Depends(require_permission(CONFIG_WRITE))) -> dict:
    """Most-overridden rules across this org's runs — the tuning signal for the
    rulebook.

    Aggregates RULE_OVERRIDE audit events into a ranked list of which rules
    humans most often correct, and to which path. A rule that's overridden a lot
    is a rule whose thresholds are wrong for this org — fix it in the editor.
    Reflects runs currently in the store (a durable backend persists them;
    in-memory loses them on restart)."""
    store = get_store()
    by_rule: dict[str, dict] = {}
    total = 0
    runs_scanned = 0
    for rid in store.list_ids():
        state = store.get(rid)
        if state is None:
            continue
        if principal.subject != "dev" and state.get("tenant_id") != principal.tenant_id:
            continue
        runs_scanned += 1
        for ev in state.get("audit_events", []):
            if _ev_type(ev) != AuditEventType.RULE_OVERRIDE.value:
                continue
            md = _ev_meta(ev)
            rule_id = md.get("original_rule_id") or "unknown"
            new_path = md.get("new_path") or "unknown"
            rec = by_rule.setdefault(rule_id, {"rule_id": rule_id, "count": 0, "to_paths": {}})
            rec["count"] += 1
            rec["to_paths"][new_path] = rec["to_paths"].get(new_path, 0) + 1
            total += 1
    ranked = sorted(by_rule.values(), key=lambda r: r["count"], reverse=True)
    return {"total_overrides": total, "runs_scanned": runs_scanned, "rules": ranked}
