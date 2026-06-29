"""Durable run-execution queue (DB-backed).

Backs `RUN_QUEUE_ENABLED` mode: instead of executing an uploaded run as a
fire-and-forget asyncio task (lost on restart), the run's input is persisted to
the `run_jobs` table and a worker leases + executes it. This makes runs:

  * durable      — a queued run survives a process restart,
  * recoverable  — a run whose worker died mid-flight is re-leased (lease TTL),
  * retryable    — a failed execution is retried up to `max_attempts`.

Claiming is race-safe across SQLite and Postgres without dialect-specific
locking: we read one candidate, then issue a conditional UPDATE guarded by the
status we saw and check `rowcount == 1`. Whoever's UPDATE lands first wins; the
loser simply tries the next candidate.
"""
from __future__ import annotations

import gzip
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update

from app.config import get_settings
from app.db import models as m
from app.db.session import session_scope

log = logging.getLogger("ap_agent.job_queue")

# Upper bound on retry backoff regardless of attempt count.
_MAX_BACKOFF_SECONDS = 300.0


@dataclass
class ClaimedJob:
    run_id: str
    tenant_id: str
    filename: str
    content: bytes
    attempts: int
    max_attempts: int


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(*, run_id: str, tenant_id: str, filename: str, content: bytes, max_attempts: int = 3) -> None:
    """Persist an uploaded run as a queued job (input stored gzipped)."""
    blob = gzip.compress(content)
    with session_scope() as s:
        existing = s.get(m.RunJob, run_id)
        if existing is not None:
            # Re-submitting the same id re-queues it (idempotent).
            existing.queue_status = "queued"
            existing.input_gz = blob
            existing.filename = filename
            existing.tenant_id = tenant_id
            existing.leased_by = None
            existing.leased_at = None
            existing.available_at = None  # re-submit is claimable immediately
            return
        s.add(
            m.RunJob(
                run_id=run_id,
                tenant_id=tenant_id,
                filename=filename,
                input_gz=blob,
                queue_status="queued",
                attempts=0,
                max_attempts=max_attempts,
            )
        )


def reclaim_stale(lease_ttl_seconds: int) -> int:
    """Recover `running` jobs whose lease has expired.

    A live worker keeps its lease fresh (see :func:`renew_lease`); only a job
    whose worker died lets `leased_at` age past the TTL. Such a job is either
    requeued (attempts remain) or marked `failed` (attempts exhausted). The
    second case is essential: without it, a job that crashes its worker every
    time would be re-leased forever — a poison pill that never hits max_attempts
    because the failure-path counter (`mark_failed_or_retry`) is never reached.

    Run on startup (jobs a dead process left `running` are orphaned) and
    periodically by the worker."""
    cutoff = _now() - timedelta(seconds=lease_ttl_seconds)
    with session_scope() as s:
        # Exhausted: give up instead of re-leasing forever.
        failed = s.execute(
            update(m.RunJob)
            .where(
                m.RunJob.queue_status == "running",
                m.RunJob.leased_at < cutoff,
                m.RunJob.attempts >= m.RunJob.max_attempts,
            )
            .values(
                queue_status="failed",
                leased_by=None,
                leased_at=None,
                last_error="lease expired after max attempts (worker died mid-run repeatedly)",
            )
        ).rowcount or 0
        # Still retryable: back to the queue.
        requeued = s.execute(
            update(m.RunJob)
            .where(
                m.RunJob.queue_status == "running",
                m.RunJob.leased_at < cutoff,
                m.RunJob.attempts < m.RunJob.max_attempts,
            )
            .values(queue_status="queued", leased_by=None, leased_at=None)
        ).rowcount or 0
    if failed or requeued:
        log.warning(
            "job_queue: reclaimed stale running job(s) (requeued=%d, failed=%d, lease_ttl=%ds)",
            requeued, failed, lease_ttl_seconds,
        )
    return requeued + failed


def claim_next(*, worker_id: str) -> ClaimedJob | None:
    """Atomically claim the oldest queued job for this worker, or None.

    Race-safe: the conditional UPDATE (guarded by queue_status='queued') only
    succeeds for one caller; a loser returns None and the worker loops."""
    with session_scope() as s:
        now = _now()
        candidate = s.execute(
            select(m.RunJob)
            .where(
                m.RunJob.queue_status == "queued",
                m.RunJob.attempts < m.RunJob.max_attempts,
                # Skip jobs still inside their retry-backoff window.
                or_(m.RunJob.available_at.is_(None), m.RunJob.available_at <= now),
            )
            .order_by(m.RunJob.created_at)
            .limit(1)
        ).scalar_one_or_none()
        if candidate is None:
            return None

        res = s.execute(
            update(m.RunJob)
            .where(
                m.RunJob.run_id == candidate.run_id,
                m.RunJob.queue_status == "queued",
                # Re-check under the conditional update: never claim a job that
                # has already used all its attempts (defends against a requeue
                # that slipped an exhausted job back to 'queued').
                m.RunJob.attempts < m.RunJob.max_attempts,
            )
            .values(
                queue_status="running",
                leased_by=worker_id,
                leased_at=_now(),
                attempts=m.RunJob.attempts + 1,
            )
        )
        if (res.rowcount or 0) != 1:
            return None  # lost the race; caller will retry the loop

        job = s.get(m.RunJob, candidate.run_id)
        assert job is not None
        return ClaimedJob(
            run_id=job.run_id,
            tenant_id=job.tenant_id,
            filename=job.filename,
            content=gzip.decompress(job.input_gz),
            attempts=job.attempts,
            max_attempts=job.max_attempts,
        )


def renew_lease(run_id: str, worker_id: str) -> bool:
    """Refresh the lease on a still-running job so a legitimately long execution
    isn't reclaimed — and double-executed — while its worker is alive.

    Returns False if this worker no longer holds the lease (e.g. it was already
    reclaimed during a stall), signalling the worker to stop heartbeating."""
    with session_scope() as s:
        res = s.execute(
            update(m.RunJob)
            .where(
                m.RunJob.run_id == run_id,
                m.RunJob.leased_by == worker_id,
                m.RunJob.queue_status == "running",
            )
            .values(leased_at=_now())
        )
    return (res.rowcount or 0) == 1


def mark_done(run_id: str) -> None:
    with session_scope() as s:
        job = s.get(m.RunJob, run_id)
        if job is not None:
            job.queue_status = "done"
            job.leased_by = None
            job.leased_at = None


def mark_failed_or_retry(run_id: str, *, error: str) -> str:
    """On execution failure: requeue if attempts remain, else mark failed.

    Returns the resulting queue_status ('queued' or 'failed')."""
    with session_scope() as s:
        job = s.get(m.RunJob, run_id)
        if job is None:
            return "failed"
        job.last_error = (error or "")[:2000]
        if job.attempts < job.max_attempts:
            # Exponential backoff on the attempt just consumed (attempts is the
            # 1-based count after the claim), so a fast-failing job doesn't burn
            # its remaining attempts in a fraction of a second of tight polling.
            base = max(0.0, get_settings().run_queue_retry_backoff_seconds)
            delay = min(base * (2 ** (job.attempts - 1)), _MAX_BACKOFF_SECONDS)
            job.queue_status = "queued"
            job.leased_by = None
            job.leased_at = None
            job.available_at = _now() + timedelta(seconds=delay) if delay > 0 else None
            return "queued"
        job.queue_status = "failed"
        job.leased_by = None
        job.leased_at = None
        return "failed"


def queue_depth() -> dict[str, int]:
    """Count jobs by queue_status (for /metrics and readiness visibility)."""
    with session_scope() as s:
        rows = s.execute(
            select(m.RunJob.queue_status, m.RunJob.run_id)
        ).all()
    counts: dict[str, int] = {}
    for status, _ in rows:
        counts[status] = counts.get(status, 0) + 1
    return counts
