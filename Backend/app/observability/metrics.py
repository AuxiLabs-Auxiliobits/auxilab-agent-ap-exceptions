"""In-process metrics registry — no external dependency.

Tracks counters/sums the operator actually needs (runs, AI calls, tokens,
estimated cost, comms sends) and renders them in Prometheus text-exposition
format at GET /metrics. Process-local (per replica); a Prometheus scrape
aggregates across replicas. Swap for prometheus_client if you outgrow this.

AI cost is estimated from a small price table (USD per 1M tokens). Prices drift
— treat the numbers as directional for budget alerting, not billing-grade.
"""
from __future__ import annotations

import threading

# USD per 1,000,000 tokens (input, output). Substring-matched against model id
# so "claude-opus-4-7", "claude-opus-4-7-20250930" etc. all resolve.
_PRICE_TABLE: list[tuple[str, float, float]] = [
    ("claude-opus", 15.0, 75.0),
    ("claude-sonnet", 3.0, 15.0),
    ("claude-haiku", 0.80, 4.0),
    ("gemini-2.5-pro", 1.25, 10.0),
    ("gemini-2.5-flash", 0.30, 2.50),
    ("gemini", 0.30, 2.50),
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4o", 2.50, 10.0),
]


def estimate_cost_usd(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Best-effort cost estimate. Unknown models (incl. mock) cost 0."""
    mid = (model_id or "").lower()
    for needle, in_price, out_price in _PRICE_TABLE:
        if needle in mid:
            return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price
    return 0.0


class _Registry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def snapshot(self) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
        with self._lock:
            return dict(self._counters)

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()


_REGISTRY = _Registry()


# ---------------------------------------------------------------------- #
# Recording helpers (called from the pipeline / client / dispatcher)      #
# ---------------------------------------------------------------------- #


def record_ai_usage(*, provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    """Record one AI call's token usage + estimated cost. Returns the cost."""
    cost = estimate_cost_usd(model, input_tokens, output_tokens)
    _REGISTRY.inc("ap_ai_calls_total", 1.0, provider=provider)
    _REGISTRY.inc("ap_ai_tokens_total", float(input_tokens), provider=provider, type="input")
    _REGISTRY.inc("ap_ai_tokens_total", float(output_tokens), provider=provider, type="output")
    _REGISTRY.inc("ap_ai_cost_usd_total", cost, provider=provider)
    return cost


def record_run(*, status: str, duration_ms: float) -> None:
    _REGISTRY.inc("ap_runs_total", 1.0, status=status)
    _REGISTRY.inc("ap_run_duration_ms_sum", duration_ms, status=status)


def record_comms_send(*, status: str, provider: str) -> None:
    _REGISTRY.inc("ap_comms_sends_total", 1.0, status=status, provider=provider)


def reset() -> None:
    """Test helper — clear all counters."""
    _REGISTRY.reset()


# ---------------------------------------------------------------------- #
# Prometheus text exposition                                              #
# ---------------------------------------------------------------------- #


def render_prometheus() -> str:
    """Render the registry in Prometheus text-exposition format."""
    snap = _REGISTRY.snapshot()
    # Group by metric name so each gets a single # TYPE header.
    by_name: dict[str, list[tuple[tuple[tuple[str, str], ...], float]]] = {}
    for (name, labels), value in snap.items():
        by_name.setdefault(name, []).append((labels, value))

    lines: list[str] = []
    for name in sorted(by_name):
        lines.append(f"# TYPE {name} counter")
        for labels, value in sorted(by_name[name]):
            if labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in labels)
                lines.append(f"{name}{{{label_str}}} {value}")
            else:
                lines.append(f"{name} {value}")
    return "\n".join(lines) + "\n"
