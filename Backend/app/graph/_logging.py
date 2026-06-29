"""Structured step-level logging helpers for LangGraph nodes.

Every node uses `step_log(node_name, state)` as a context manager so that
entry, exit, duration, and run_id are emitted consistently — making the
pipeline trivially traceable from a single `tail -f`.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

log = logging.getLogger("ap_agent.step")


@contextmanager
def step_log(node_name: str, state: Mapping[str, Any]) -> Iterator[dict[str, Any]]:
    """Emit START / END (or ERROR) log lines around a node body.

    The yielded dict can be populated with key=value pairs by the caller;
    they'll appear in the END log line. Example::

        with step_log("classify_node", state) as info:
            ...
            info["rows"] = len(rows)
            info["provider"] = "gemini"
    """
    run_id = state.get("run_id", "?")
    info: dict[str, Any] = {}
    log.info("▶ %s start run_id=%s", node_name, run_id)
    t0 = time.perf_counter()
    try:
        yield info
    except Exception as e:
        dt_ms = (time.perf_counter() - t0) * 1000
        log.exception(
            "✖ %s ERROR run_id=%s duration_ms=%.1f err=%s",
            node_name,
            run_id,
            dt_ms,
            e,
        )
        raise
    dt_ms = (time.perf_counter() - t0) * 1000
    kv = " ".join(f"{k}={v}" for k, v in info.items())
    log.info(
        "✔ %s end   run_id=%s duration_ms=%.1f %s",
        node_name,
        run_id,
        dt_ms,
        kv,
    )
