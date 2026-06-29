"""LangGraph StateGraph assembly.

Topology:

    START
      │
      ▼
    ingest_node ──► (FAILED)────────► END
      │
      ▼
    classify_node (AI)
      │
      ▼
    severity_validator
      │
      ▼
    route_node (rules)
      │
      ├──(requires comms)──► draft_node (AI) ──┐
      │                                         │
      └──(no comms)─────────────────────────────┤
                                                │
                                                ▼
                                        prioritize_node
                                                │
                                                ▼
                                          persist_node
                                                │
                                                ▼
                                               END

Per-row failures inside classify / draft are absorbed by the nodes
themselves (degraded mode). Catastrophic ingest failures short-circuit
to END with status=FAILED.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.graph.nodes.classify import classify_node
from app.graph.nodes.draft import draft_node, requires_comms
from app.graph.nodes.error_handler import error_handler
from app.graph.nodes.ingest import ingest_node
from app.graph.nodes.persist import persist_node
from app.graph.nodes.prioritize import prioritize_node
from app.graph.nodes.route import route_node
from app.graph.nodes.severity import severity_validator
from app.graph.nodes.vendor_update import vendor_update_node
from app.graph.state import RunState
from app.schemas import RunStatus


def _after_ingest(state: RunState) -> str:
    return "error_handler" if state.get("status") == RunStatus.FAILED else "classify_node"


def _after_route(state: RunState) -> str:
    return "draft_node" if requires_comms(state) else "prioritize_node"


def build_graph() -> Any:
    g = StateGraph(RunState)

    g.add_node("ingest_node", ingest_node)
    g.add_node("classify_node", classify_node)
    g.add_node("severity_validator", severity_validator)
    g.add_node("route_node", route_node)
    g.add_node("draft_node", draft_node)
    g.add_node("prioritize_node", prioritize_node)
    g.add_node("vendor_update_node", vendor_update_node)
    g.add_node("persist_node", persist_node)
    g.add_node("error_handler", error_handler)

    g.add_edge(START, "ingest_node")
    g.add_conditional_edges(
        "ingest_node",
        _after_ingest,
        {"error_handler": "error_handler", "classify_node": "classify_node"},
    )
    g.add_edge("classify_node", "severity_validator")
    g.add_edge("severity_validator", "route_node")
    g.add_conditional_edges(
        "route_node",
        _after_route,
        {"draft_node": "draft_node", "prioritize_node": "prioritize_node"},
    )
    g.add_edge("draft_node", "prioritize_node")
    g.add_edge("prioritize_node", "vendor_update_node")
    g.add_edge("vendor_update_node", "persist_node")
    g.add_edge("persist_node", END)
    g.add_edge("error_handler", END)

    return g.compile()


def initial_state(run_id: str, tenant_id: str, owner: str | None = None) -> RunState:
    state: RunState = {
        "run_id": run_id,
        "tenant_id": tenant_id,
        "owner": owner or "",
        "created_at": datetime.now(UTC),
        "rows": [],
        "quarantined": [],
        "classifications": [],
        "resolutions": [],
        "drafts": [],
        "errors": [],
        "audit_events": [],
        "status": RunStatus.PENDING,
        "current_node": "START",
    }
    # Resolve the effective settings for this tenant once, up front, and stash it
    # as a transient (stripped before persistence). The AI nodes read it so a run
    # uses the org's own BYOK provider config. With PER_ORG_CONFIG_ENABLED off
    # (default) this is just the env Settings — identical to prior behaviour.
    from app.api.org_config import resolve_settings

    state["_settings"] = resolve_settings(tenant_id)  # type: ignore[typeddict-unknown-key]
    return state
