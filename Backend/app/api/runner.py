"""Run executor.

Two entrypoints:

  submit_run(...)   — non-blocking. Schedules the pipeline as a background
                      task and returns run_id immediately. State is written
                      to the store after every LangGraph node so polling
                      clients see live progress (current_node, accumulating
                      counts, etc.). This is what POST /v1/runs uses.

  execute_run(...)  — blocking. Runs the pipeline synchronously and returns
                      the final state. Used by tests and offline scripts.

Both share `_execute_streaming` which uses `graph.stream(stream_mode="values")`
so the in-memory store is updated after every node, regardless of whether
the run is foreground or background.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import UTC, datetime

from app.api.store import RunStore
from app.config import get_settings
from app.graph.builder import build_graph, initial_state
from app.graph.state import RunState
from app.schemas import RunStatus

log = logging.getLogger("ap_agent.runner")

_GRAPH = None
# Hold strong references so background tasks aren't garbage-collected
# while still running.
_BG_TASKS: set[asyncio.Task] = set()


def get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    return _GRAPH


async def drain_background_tasks(timeout: float = 30.0) -> None:
    """Wait (up to ``timeout`` seconds) for in-flight background runs to finish.

    Called from the FastAPI shutdown hook so a deploy/SIGTERM doesn't abandon a
    run mid-pipeline. Each node persists to the store as it completes, so a run
    that doesn't finish in time is still recoverable from its last checkpoint;
    this just gives near-done runs a chance to reach a terminal status cleanly.
    """
    tasks = [t for t in _BG_TASKS if not t.done()]
    if not tasks:
        return
    log.info("Draining %d in-flight run task(s) (timeout=%.0fs)…", len(tasks), timeout)
    done, pending = await asyncio.wait(tasks, timeout=timeout)
    if pending:
        log.warning(
            "%d run task(s) did not finish within %.0fs — last checkpoint is "
            "persisted in the store; they will show non-terminal status.",
            len(pending),
            timeout,
        )
    else:
        log.info("All background run tasks drained cleanly.")


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


def _strip_transients(snap: dict) -> dict:
    """Remove in-memory-only fields before persisting to the store."""
    s = dict(snap)
    s.pop("_input_bytes", None)
    s.pop("_input_filename", None)
    s.pop("_settings", None)  # resolved per-run Settings object — never persisted
    return s


def _record_run_metric(status: str, duration_ms: float) -> None:
    try:
        from app.observability import record_run

        # status may be "RunStatus.AWAITING_REVIEW" or the enum's value — normalize.
        record_run(status=status.split(".")[-1], duration_ms=duration_ms)
    except Exception:  # noqa: BLE001 — metrics must never break a run
        log.debug("metrics: record_run failed", exc_info=True)


def _execute_streaming(
    state: RunState, store: RunStore, run_id: str
) -> RunState:
    """Run the graph and update the store after every node.

    Runs synchronously — when called from `submit_run` this executes inside
    a thread-pool executor so the asyncio event loop stays free.
    """
    t0 = time.perf_counter()
    final: RunState = state
    try:
        graph = get_graph()
        for snap in graph.stream(state, stream_mode="values"):
            view = _strip_transients(snap)
            store.put(view)
            final = view
    except Exception as e:
        dt_ms = (time.perf_counter() - t0) * 1000
        log.exception(
            "✖ RUN FAILED run_id=%s duration_ms=%.1f err=%s", run_id, dt_ms, e
        )
        final = _strip_transients(final)
        final["status"] = RunStatus.FAILED
        store.put(final)
        _record_run_metric("FAILED", dt_ms)
        return final

    dt_ms = (time.perf_counter() - t0) * 1000
    final = _strip_transients(final)
    if final.get("status") != RunStatus.FAILED:
        final["status"] = RunStatus.AWAITING_REVIEW
    final["completed_at"] = datetime.now(UTC)
    store.put(final)
    _record_run_metric(str(final["status"]), dt_ms)

    metrics = final.get("metrics")
    log.info(
        "═══ RUN END   run_id=%s status=%s duration_ms=%.1f rows=%d "
        "quarantined=%d classified=%d routed=%d drafted=%d auto=%s escal=%s ═══",
        run_id,
        final["status"],
        dt_ms,
        len(final.get("rows", [])),
        len(final.get("quarantined", [])),
        len(final.get("classifications", [])),
        len(final.get("resolutions", [])),
        len(final.get("drafts", [])),
        metrics.auto_resolvable_count if metrics else "?",
        metrics.escalations_required if metrics else "?",
    )
    return final


async def submit_run(
    *,
    content: bytes,
    filename: str,
    tenant_id: str,
    store: RunStore,
    owner: str | None = None,
) -> str:
    """Schedule a run as a background task. Returns the run_id immediately.

    The first store.put happens synchronously before this returns, so
    `GET /v1/runs/{id}` reflects RUNNING status the moment this returns.
    """
    run_id = new_run_id()
    log.info(
        "═══ RUN SCHEDULED run_id=%s tenant=%s file=%s bytes=%d ═══",
        run_id,
        tenant_id,
        filename,
        len(content),
    )

    # Durable path: persist the input to the run_jobs queue and let the worker
    # execute it. The run survives a restart; a crashed run is re-leased.
    if get_settings().run_queue_enabled:
        from app.api import job_queue

        state = initial_state(run_id, tenant_id, owner=owner)
        state["status"] = RunStatus.PENDING  # queued, awaiting a worker
        store.put(_strip_transients(state))
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: job_queue.enqueue(
                run_id=run_id,
                tenant_id=tenant_id,
                filename=filename,
                content=content,
                max_attempts=get_settings().run_queue_max_attempts,
            ),
        )
        return run_id

    # Legacy in-process path (in-memory store / queue disabled): run as a
    # fire-and-forget background task. Not durable across restarts.
    state = initial_state(run_id, tenant_id, owner=owner)
    state["_input_bytes"] = content  # type: ignore[typeddict-unknown-key]
    state["_input_filename"] = filename  # type: ignore[typeddict-unknown-key]
    state["status"] = RunStatus.RUNNING
    # Make the run visible to GET endpoints immediately, before any node runs.
    store.put(_strip_transients(state))

    async def _bg():
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None, _execute_streaming, state, store, run_id
            )
        except Exception:
            # _execute_streaming already swallows + records to store; this
            # is a defensive backstop for executor-level failures.
            log.exception("Background runner crashed for run_id=%s", run_id)

    task = asyncio.create_task(_bg())
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return run_id


def execute_run(
    *,
    content: bytes,
    filename: str,
    tenant_id: str,
    store: RunStore,
) -> RunState:
    """Synchronous execution. Returns the final state.

    Kept for tests and any caller that wants a blocking result. New code
    should prefer `submit_run` + polling.
    """
    run_id = new_run_id()
    log.info("═══ RUN START (sync) run_id=%s ═══", run_id)
    state: RunState = initial_state(run_id, tenant_id)
    state["_input_bytes"] = content  # type: ignore[typeddict-unknown-key]
    state["_input_filename"] = filename  # type: ignore[typeddict-unknown-key]
    state["status"] = RunStatus.RUNNING
    store.put(_strip_transients(state))
    return _execute_streaming(state, store, run_id)


def execute_job(
    *,
    run_id: str,
    content: bytes,
    filename: str,
    tenant_id: str,
    store: RunStore,
) -> RunState:
    """Execute a queued job under a known run_id (used by the durable worker).

    Like `execute_run` but the run_id is supplied by the queue rather than
    minted here, so the persisted job and the run store agree on one id.
    """
    state: RunState = initial_state(run_id, tenant_id)
    state["_input_bytes"] = content  # type: ignore[typeddict-unknown-key]
    state["_input_filename"] = filename  # type: ignore[typeddict-unknown-key]
    state["status"] = RunStatus.RUNNING
    store.put(_strip_transients(state))
    return _execute_streaming(state, store, run_id)
