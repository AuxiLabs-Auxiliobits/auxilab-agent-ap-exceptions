"""Route node — deterministic rules engine."""
from __future__ import annotations

import logging
from collections import Counter

from app.audit.logger import make_event
from app.config import get_settings
from app.graph.state import RunState
from app.rules.engine import Policy, RulesEngine, load_policy, to_decimal
from app.schemas import (
    AuditEventType,
    ClassificationResult,
    ExceptionRow,
    ResolutionDecision,
)

log = logging.getLogger("ap_agent.route")


_DEFAULT_POLICY: Policy | None = None


def _default_policy() -> Policy:
    """The global default policy, parsed once per process."""
    global _DEFAULT_POLICY
    if _DEFAULT_POLICY is None:
        _DEFAULT_POLICY = load_policy(get_settings().rules_policy_path)
    return _DEFAULT_POLICY


def _engine_for(tenant_id: str | None) -> tuple[RulesEngine, bool]:
    """Resolve the rules engine for a tenant: its custom rulebook if configured,
    else the global default. Returns (engine, is_custom). Never raises — a policy
    lookup failure falls back to the default so a run is never broken."""
    if tenant_id:
        try:
            from app.api import org_policy

            custom = org_policy.get_policy(tenant_id)
            if custom is not None:
                return RulesEngine(custom), True
        except Exception:  # noqa: BLE001 — policy resolution must never break a run
            log.warning(
                "route: per-org policy lookup failed for tenant=%s; using default",
                tenant_id, exc_info=True,
            )
    return RulesEngine(_default_policy()), False


def route_node(state: RunState) -> RunState:
    from app.graph._logging import step_log

    rows: list[ExceptionRow] = list(state.get("rows", []))
    classifications: list[ClassificationResult] = list(state.get("classifications", []))
    audit = list(state.get("audit_events", []))

    row_by_id = {r.invoice_id: r for r in rows}
    engine, policy_is_custom = _engine_for(state.get("tenant_id"))

    # Materiality guardrail (per-org when org config resolves it): an invoice at or
    # above this amount can never auto-approve, regardless of the policy.
    settings = state.get("_settings") or get_settings()
    ceiling = (
        to_decimal(settings.auto_approve_max_amount)
        if settings.auto_approve_max_amount and settings.auto_approve_max_amount > 0
        else None
    )

    with step_log("route_node", state) as info:
        log.info(
            "route: evaluating rows=%d policy_version=%s rules=%d source=%s",
            len(classifications),
            engine.policy.version,
            len(engine.policy.rules),
            "org" if policy_is_custom else "default",
        )

        decisions: list[ResolutionDecision] = []

        audit.append(
            make_event(
                run_id=state["run_id"],
                node_name="route_node",
                event_type=AuditEventType.NODE_START,
                metadata={
                    "rule_version": engine.policy.version,
                    "policy_source": "org" if policy_is_custom else "default",
                },
            )
        )

        for c in classifications:
            row = row_by_id.get(c.invoice_id)
            if row is None:
                continue
            decision = engine.evaluate(row, c, auto_approve_ceiling=ceiling)
            decisions.append(decision)
            log.debug(
                "route: invoice=%s type=%s → rule=%s path=%s comms=%s sla=%dh",
                row.invoice_id,
                c.primary_exception_type.value,
                decision.rule_id,
                decision.resolution_path.value,
                decision.requires_communication,
                decision.sla_hours,
            )
            audit.append(
                make_event(
                    run_id=state["run_id"],
                    node_name="route_node",
                    event_type=AuditEventType.RULE_FIRE,
                    invoice_id=row.invoice_id,
                    output_payload=decision.model_dump(mode="json"),
                    metadata={"rule_id": decision.rule_id},
                )
            )

        rule_counts = Counter(d.rule_id for d in decisions)
        path_counts = Counter(d.resolution_path.value for d in decisions)
        log.info(
            "route: routed=%d by_rule=%s by_path=%s comms_needed=%d",
            len(decisions),
            dict(rule_counts),
            dict(path_counts),
            sum(1 for d in decisions if d.requires_communication),
        )

        audit.append(
            make_event(
                run_id=state["run_id"],
                node_name="route_node",
                event_type=AuditEventType.NODE_END,
                metadata={"routed": len(decisions)},
            )
        )

        info["routed"] = len(decisions)
        info["comms"] = sum(1 for d in decisions if d.requires_communication)

    out = dict(state)
    out["resolutions"] = decisions
    out["audit_events"] = audit
    out["current_node"] = "route_node"
    return out
