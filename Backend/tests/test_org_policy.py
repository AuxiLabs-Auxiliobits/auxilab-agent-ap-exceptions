"""Per-org resolution rulebook: storage, validation, API, and route resolution."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.schemas import (
    ClassificationResult,
    ExceptionRow,
    PrimaryExceptionType,
    ResolutionPath,
    Severity,
)

# A deliberately lenient custom rulebook: auto-approve ANY price variance. Under
# the global default, a 12% variance escalates — so routing differs by policy.
CUSTOM_POLICY = {
    "version": "acme.1",
    "rules": [
        {
            "id": "acme_pv_auto",
            "when": {"exception_type": "Price Variance"},
            "then": {"resolution_path": "AUTO_APPROVE", "requires_communication": False, "sla_hours": 12},
        },
        {
            "id": "catch_all",
            "when": {},
            "then": {"resolution_path": "MANUAL_REVIEW", "requires_communication": False, "sla_hours": 72},
        },
    ],
}

# Same rules but missing the mandatory catch-all (last rule has a condition).
UNSAFE_POLICY = {
    "version": "bad.1",
    "rules": [
        {
            "id": "only_rule",
            "when": {"exception_type": "Price Variance"},
            "then": {"resolution_path": "AUTO_APPROVE", "requires_communication": False, "sla_hours": 12},
        },
    ],
}


@pytest.fixture
def policy_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("RUN_STORE_BACKEND", "memory")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{tmp_path.as_posix()}/pol.db")
    for k in ("SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.setenv(k, "")

    from app.api import org_policy
    from app.config import get_settings
    from app.db import session as db_session

    get_settings.cache_clear()
    db_session.reset_engine()
    org_policy._table_ensured = False
    yield
    get_settings.cache_clear()
    db_session.reset_engine()
    org_policy._table_ensured = False


def _row(amount="5000", desc="Invoice exceeds PO by 12%") -> ExceptionRow:
    return ExceptionRow(
        invoice_id="INV-1", vendor_name="Acme", invoice_amount=Decimal(amount),
        po_number="PO-1", exception_type="Price Variance",
        exception_description=desc, days_outstanding=10,
    )


def _classification() -> ClassificationResult:
    return ClassificationResult(
        invoice_id="INV-1", primary_exception_type=PrimaryExceptionType.PRICE_VARIANCE,
        root_cause="rc", severity_ai_suggested=Severity.HIGH, severity=Severity.HIGH,
        confidence_score=0.9, rationale="r", model_id="mock", prompt_version="v1",
    )


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #
def test_store_roundtrip_and_validation(policy_env):
    from app.api import org_policy

    assert org_policy.get_policy("acme") is None  # no custom → default

    policy = org_policy.upsert("acme", CUSTOM_POLICY, actor="admin")
    assert policy.version == "acme.1"

    fetched = org_policy.get_policy("acme")
    assert fetched is not None and fetched.rules[0].id == "acme_pv_auto"

    # Unsafe policy (no catch-all) is rejected on write — never stored.
    with pytest.raises(ValueError):
        org_policy.upsert("acme", UNSAFE_POLICY, actor="admin")

    assert org_policy.delete("acme") is True
    assert org_policy.get_policy("acme") is None


# --------------------------------------------------------------------------- #
# Route resolution
# --------------------------------------------------------------------------- #
def test_route_node_uses_custom_policy(policy_env):
    from app.api import org_policy
    from app.graph.nodes.route import route_node

    state = {
        "run_id": "run_test", "tenant_id": "acme",
        "rows": [_row()], "classifications": [_classification()], "audit_events": [],
    }

    # Default policy: a 12% variance escalates to the controller.
    out = route_node(dict(state))
    assert out["resolutions"][0].resolution_path == ResolutionPath.ESCALATE_CONTROLLER

    # With the org's lenient policy stored, the SAME invoice auto-approves.
    org_policy.upsert("acme", CUSTOM_POLICY, actor="admin")
    out = route_node(dict(state))
    dec = out["resolutions"][0]
    assert dec.resolution_path == ResolutionPath.AUTO_APPROVE
    assert dec.rule_id == "acme_pv_auto"

    # A different tenant with no custom policy still gets the default.
    other = dict(state)
    other["tenant_id"] = "other"
    assert route_node(other)["resolutions"][0].resolution_path == ResolutionPath.ESCALATE_CONTROLLER


def test_custom_policy_still_bounded_by_materiality_ceiling(policy_env):
    """A lenient org policy can't bypass the global materiality guardrail."""
    from app.api import org_policy
    from app.graph.nodes.route import route_node

    org_policy.upsert("acme", CUSTOM_POLICY, actor="admin")
    # $50k price variance: the org rule says auto-approve, but the $10k ceiling
    # forces manual review regardless.
    state = {
        "run_id": "r", "tenant_id": "acme",
        "rows": [_row(amount="50000")], "classifications": [_classification()],
        "audit_events": [],
    }
    dec = route_node(state)["resolutions"][0]
    assert dec.resolution_path == ResolutionPath.MANUAL_REVIEW
    assert "materiality_ceiling" in dec.rule_id


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_rules_api_roundtrip(policy_env):
    from fastapi.testclient import TestClient

    from app.api.main import app

    c = TestClient(app)

    # Default to start.
    r = c.get("/v1/org/rules")
    assert r.status_code == 200 and r.json()["is_custom"] is False

    # Validate endpoint: good vs unsafe.
    assert c.post("/v1/org/rules/validate", json=CUSTOM_POLICY).json()["ok"] is True
    bad = c.post("/v1/org/rules/validate", json=UNSAFE_POLICY).json()
    assert bad["ok"] is False and "catch-all" in bad["error"].lower()

    # Save a custom policy, then read it back.
    assert c.put("/v1/org/rules", json={"policy": CUSTOM_POLICY}).status_code == 200
    got = c.get("/v1/org/rules").json()
    assert got["is_custom"] is True and got["policy"]["version"] == "acme.1"

    # Saving an unsafe policy is rejected.
    assert c.put("/v1/org/rules", json=UNSAFE_POLICY).status_code == 422

    # Revert.
    assert c.delete("/v1/org/rules").json()["had_custom"] is True
    assert c.get("/v1/org/rules").json()["is_custom"] is False


def test_resolution_override_and_report(policy_env):
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.api.store import get_store, reset_store_cache
    from app.schemas import ResolutionDecision, ResolutionPath

    reset_store_cache()
    store = get_store()
    store.put(
        {
            "run_id": "run_ovr", "tenant_id": "default", "status": "AWAITING_REVIEW",
            "created_at": "2026-06-19T00:00:00+00:00",
            "rows": [], "classifications": [], "drafts": [], "audit_events": [],
            "resolutions": [
                ResolutionDecision(
                    invoice_id="INV-9", resolution_path=ResolutionPath.AUTO_APPROVE,
                    rule_id="pv_auto_approve_small", rule_version="2026.05.1",
                    rule_trace=["MATCHED pv_auto_approve_small"],
                    requires_communication=False, sla_hours=24,
                )
            ],
        }
    )
    c = TestClient(app)

    # A reason is required; the path must be valid.
    assert c.post("/v1/runs/run_ovr/resolutions/INV-9/override",
                  json={"resolution_path": "MANUAL_REVIEW"}).status_code == 422
    assert c.post("/v1/runs/run_ovr/resolutions/INV-9/override",
                  json={"resolution_path": "NOPE", "reason": "x"}).status_code == 400

    # Override the routing with a reason → 200, path updated, marked as override.
    r = c.post("/v1/runs/run_ovr/resolutions/INV-9/override",
               json={"resolution_path": "ESCALATE_CONTROLLER", "reason": "material to us"})
    assert r.status_code == 200
    body = r.json()
    assert body["resolution_path"] == "ESCALATE_CONTROLLER"
    assert body["original_rule_id"] == "pv_auto_approve_small"

    # The stored resolution reflects the override.
    state = store.get("run_ovr")
    dec = state["resolutions"][0]
    assert dec.resolution_path == ResolutionPath.ESCALATE_CONTROLLER
    assert "human_override" in dec.rule_id

    # The most-overridden report surfaces it as a tuning signal.
    rep = c.get("/v1/org/rules/overrides").json()
    assert rep["total_overrides"] >= 1
    top = rep["rules"][0]
    assert top["rule_id"] == "pv_auto_approve_small"
    assert top["to_paths"].get("ESCALATE_CONTROLLER", 0) >= 1


def test_rules_simulate_diffs_candidate_vs_current(policy_env):
    from fastapi.testclient import TestClient

    from app.api.main import app
    from app.api.store import get_store, reset_store_cache

    reset_store_cache()
    get_store().put(
        {
            "run_id": "run_sim", "tenant_id": "default", "status": "AWAITING_REVIEW",
            "created_at": "2026-06-19T00:00:00+00:00",
            "rows": [_row()], "classifications": [_classification()],
            "drafts": [], "audit_events": [], "resolutions": [],
        }
    )
    c = TestClient(app)

    # Current effective policy = default (a 12% variance escalates); the lenient
    # candidate auto-approves the same invoice — so the simulator shows the move.
    r = c.post("/v1/org/rules/simulate", json={"run_id": "run_sim", "policy": CUSTOM_POLICY})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert body["changed_count"] == 1
    assert body["current_distribution"] == {"ESCALATE_CONTROLLER": 1}
    assert body["simulated_distribution"] == {"AUTO_APPROVE": 1}
    ch = body["changes"][0]
    assert ch["invoice_id"] == "INV-1"
    assert ch["from"] == "ESCALATE_CONTROLLER"
    assert ch["to"] == "AUTO_APPROVE"

    # An unsafe candidate (no catch-all) is rejected before simulating.
    assert c.post(
        "/v1/org/rules/simulate", json={"run_id": "run_sim", "policy": UNSAFE_POLICY}
    ).status_code == 422

    # Unknown run → 404.
    assert c.post(
        "/v1/org/rules/simulate", json={"run_id": "nope", "policy": CUSTOM_POLICY}
    ).status_code == 404
