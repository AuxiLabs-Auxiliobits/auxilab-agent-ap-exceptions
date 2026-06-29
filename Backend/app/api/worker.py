"""Durable run worker.

A single in-process async loop that leases queued jobs from `run_jobs` and
executes them (bounded concurrency). Started/stopped by the FastAPI lifespan
when `RUN_QUEUE_ENABLED`. On startup it reclaims jobs orphaned by a previous
process; while running it periodically reclaims jobs whose worker died.

This is a pragmatic, infra-free durable runner: it needs only the existing
SQLAlchemy database, no Redis/Celery. For multi-replica throughput, run several
instances — the DB lease makes claiming safe across processes.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
import uuid

from app.api import job_queue
from app.api.runner import execute_job
from app.api.store import get_store
from app.config import get_settings
from app.schemas import RunStatus

log = logging.getLogger("ap_agent.worker")


class RunWorker:
    def __init__(self) -> None:
        s = get_settings()
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.poll = max(0.05, s.run_queue_poll_seconds)
        self.lease_ttl = s.run_queue_lease_seconds
        self.concurrency = max(1, s.run_queue_concurrency)
        self.max_attempts = s.run_queue_max_attempts
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._inflight: set[asyncio.Task] = set()
        self._reclaim_every = max(self.lease_ttl / 2, 5.0)
        self._last_reclaim = 0.0

    async def start(self) -> None:
        # Recover anything a previous process left mid-flight before we begin.
        await self._reclaim()
        self._task = asyncio.create_task(self._loop())
        log.info(
            "run worker started id=%s concurrency=%d poll=%.2fs lease_ttl=%ds",
            self.worker_id, self.concurrency, self.poll, self.lease_ttl,
        )

    async def stop(self, drain_timeout: float = 30.0) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
        if self._inflight:
            log.info("worker: draining %d in-flight job(s)…", len(self._inflight))
            _, pending = await asyncio.wait(self._inflight, timeout=drain_timeout)
            if pending:
                log.warning("worker: %d job(s) did not finish before drain timeout", len(pending))
        log.info("run worker stopped id=%s", self.worker_id)

    async def _reclaim(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: job_queue.reclaim_stale(self.lease_ttl))
        self._last_reclaim = time.monotonic()

    async def _loop(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stop.is_set():
            try:
                if len(self._inflight) >= self.concurrency:
                    await asyncio.sleep(self.poll)
                    continue
                if time.monotonic() - self._last_reclaim > self._reclaim_every:
                    await self._reclaim()
                job = await loop.run_in_executor(
                    None, lambda: job_queue.claim_next(worker_id=self.worker_id)
                )
                if job is None:
                    await asyncio.sleep(self.poll)
                    continue
                t = asyncio.create_task(self._run_job(job))
                self._inflight.add(t)
                t.add_done_callback(self._inflight.discard)
            except Exception:  # noqa: BLE001 — the loop must never die
                log.exception("worker loop iteration failed")
                await asyncio.sleep(self.poll)

    async def _heartbeat(self, run_id: str) -> None:
        """Periodically refresh this job's lease while it executes, so a long
        (but healthy) run is never reclaimed and double-executed. Renews at
        roughly a third of the TTL; stops if the lease is lost."""
        loop = asyncio.get_running_loop()
        interval = max(self.lease_ttl / 3, 5.0)
        try:
            while True:
                await asyncio.sleep(interval)
                held = await loop.run_in_executor(
                    None, lambda: job_queue.renew_lease(run_id, self.worker_id)
                )
                if not held:
                    log.warning(
                        "worker: lost lease for run_id=%s; stopping heartbeat", run_id
                    )
                    return
        except asyncio.CancelledError:
            return

    async def _run_job(self, job: job_queue.ClaimedJob) -> None:
        loop = asyncio.get_running_loop()
        store = get_store()
        log.info(
            "worker: executing run_id=%s attempt=%d/%d", job.run_id, job.attempts, job.max_attempts
        )
        heartbeat = asyncio.create_task(self._heartbeat(job.run_id))
        try:
            final = await loop.run_in_executor(
                None,
                lambda: execute_job(
                    run_id=job.run_id,
                    content=job.content,
                    filename=job.filename,
                    tenant_id=job.tenant_id,
                    store=store,
                ),
            )
            if final.get("status") == RunStatus.FAILED:
                outcome = await loop.run_in_executor(
                    None,
                    lambda: job_queue.mark_failed_or_retry(
                        job.run_id, error="run ended in FAILED status"
                    ),
                )
                log.warning("worker: run_id=%s FAILED → %s", job.run_id, outcome)
            else:
                await loop.run_in_executor(None, lambda: job_queue.mark_done(job.run_id))
        except Exception as exc:  # noqa: BLE001 — executor-level failure
            err = str(exc)
            outcome = await loop.run_in_executor(
                None, lambda: job_queue.mark_failed_or_retry(job.run_id, error=err)
            )
            log.exception("worker: run_id=%s crashed → %s", job.run_id, outcome)
        finally:
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass


_worker: RunWorker | None = None


async def start_worker() -> None:
    """Start the singleton worker if the durable queue is enabled."""
    global _worker
    if not get_settings().run_queue_enabled:
        return
    if _worker is not None:
        return
    _worker = RunWorker()
    await _worker.start()


async def stop_worker() -> None:
    global _worker
    if _worker is None:
        return
    await _worker.stop(drain_timeout=get_settings().shutdown_drain_seconds)
    _worker = None
