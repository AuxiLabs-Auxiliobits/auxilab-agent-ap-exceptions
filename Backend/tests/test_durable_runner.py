"""Tests for the DB-backed durable run queue (RUN_QUEUE_ENABLED).

Exercises the job-queue repository (enqueue / atomic claim / stale-lease reclaim
/ retry-then-fail) on a throwaway SQLite DB, plus a deterministic end-to-end run
that drives the worker's exact claim -> execute -> mark-done sequence (mock AI
mode — hermetic)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SAMPLE = Path(__file__).parent.parent / "sample_data" / "exception_queue.csv"


@pytest.fixture
def durable_db(tmp_path, monkeypatch):
    db = tmp_path / "jobs.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db.as_posix()}")
    monkeypatch.setenv("RUN_QUEUE_ENABLED", "true")
    monkeypatch.setenv("RUN_STORE_BACKEND", "db")
    monkeypatch.setenv("DB_PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("RUN_QUEUE_POLL_SECONDS", "0.05")
    # Mechanics tests claim immediately after a failure — disable retry backoff
    # so they stay deterministic (backoff itself is covered by its own test).
    monkeypatch.setenv("RUN_QUEUE_RETRY_BACKOFF_SECONDS", "0")
    # Hermetic AI + auth + vendor store.
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "AZURE_OPENAI_API_KEY",
              "AZURE_CHAT_OPENAI_ENDPOINT", "SUPABASE_URL", "SUPABASE_KEY"):
        monkeypatch.setenv(k, "")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    monkeypatch.setenv("VENDOR_PROFILES_PATH", str(tmp_path / "vendor_profiles.json"))

    from app.config import get_settings
    get_settings.cache_clear()
    from app.db.session import init_db, reset_engine
    reset_engine()
    init_db()
    from app.api import store as store_mod
    store_mod.reset_store_cache()
    from app.vendor import store as vstore_mod
    vstore_mod.reset_vendor_store()

    yield

    from app.db.session import reset_engine as _reset
    _reset()
    store_mod.reset_store_cache()
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# Queue repository
# --------------------------------------------------------------------------- #


def test_enqueue_then_claim_is_single(durable_db):
    from app.api import job_queue

    job_queue.enqueue(run_id="run_q1", tenant_id="t", filename="f.csv", content=b"a,b\n1,2\n")
    assert job_queue.queue_depth().get("queued") == 1

    claimed = job_queue.claim_next(worker_id="w1")
    assert claimed is not None
    assert claimed.run_id == "run_q1"
    assert claimed.content == b"a,b\n1,2\n"
    assert claimed.attempts == 1
    # A second claim finds nothing queued (the job is now leased/running).
    assert job_queue.claim_next(worker_id="w2") is None
    assert job_queue.queue_depth().get("running") == 1


def test_reclaim_stale_lease_requeues(durable_db):
    from app.api import job_queue
    from app.db import models as m
    from app.db.session import session_scope

    job_queue.enqueue(run_id="run_q2", tenant_id="t", filename="f.csv", content=b"x")
    job_queue.claim_next(worker_id="w1")  # -> running, leased now

    # A fresh lease is not stale.
    assert job_queue.reclaim_stale(lease_ttl_seconds=300) == 0

    # Force the lease into the past, then it should be reclaimed and re-claimable.
    with session_scope() as s:
        s.get(m.RunJob, "run_q2").leased_at = datetime.now(UTC) - timedelta(seconds=999)
    assert job_queue.reclaim_stale(lease_ttl_seconds=300) == 1
    assert job_queue.claim_next(worker_id="w2") is not None


def test_retry_then_fail(durable_db):
    from app.api import job_queue

    job_queue.enqueue(run_id="run_q3", tenant_id="t", filename="f.csv", content=b"x", max_attempts=2)
    job_queue.claim_next(worker_id="w")  # attempts = 1
    assert job_queue.mark_failed_or_retry("run_q3", error="boom") == "queued"
    job_queue.claim_next(worker_id="w")  # attempts = 2 (== max)
    assert job_queue.mark_failed_or_retry("run_q3", error="boom again") == "failed"
    assert job_queue.queue_depth().get("failed") == 1


def test_retry_backoff_holds_then_releases(durable_db, monkeypatch):
    """A failed attempt is held un-claimable until its backoff window passes."""
    from app.config import get_settings
    monkeypatch.setenv("RUN_QUEUE_RETRY_BACKOFF_SECONDS", "60")
    get_settings.cache_clear()

    from app.api import job_queue
    from app.db import models as m
    from app.db.session import session_scope

    job_queue.enqueue(run_id="run_bo", tenant_id="t", filename="f.csv", content=b"x", max_attempts=3)
    job_queue.claim_next(worker_id="w")  # attempts = 1
    assert job_queue.mark_failed_or_retry("run_bo", error="boom") == "queued"

    # Within the backoff window the job is queued but not yet claimable.
    assert job_queue.queue_depth().get("queued") == 1
    assert job_queue.claim_next(worker_id="w") is None

    # Once available_at passes, it can be claimed again (attempts advances).
    with session_scope() as s:
        s.get(m.RunJob, "run_bo").available_at = datetime.now(UTC) - timedelta(seconds=1)
    again = job_queue.claim_next(worker_id="w")
    assert again is not None and again.attempts == 2


def test_db_store_claim_draft_is_single(durable_db):
    """The DB-backed store's atomic send-claim (SELECT ... FOR UPDATE) flips a
    draft to SENDING once and refuses a second claim."""
    from app.api.store import get_store
    from app.graph.builder import initial_state
    from app.schemas import CommChannel, CommunicationDraft, SendStatus

    store = get_store()
    assert store.backend_name == "db"
    state = initial_state("run_claim", "t")
    state["drafts"] = [
        CommunicationDraft(
            invoice_id="INV-1", channel=CommChannel.VENDOR_EMAIL, recipient_hint="x",
            subject="s", body="b", template_id="t", model_id="m",
        )
    ]
    store.put(state)

    assert store.claim_draft_for_send("run_claim", "INV-1") is True
    assert store.claim_draft_for_send("run_claim", "INV-1") is False
    assert store.get("run_claim")["drafts"][0].send_status == SendStatus.SENDING


def test_mark_done(durable_db):
    from app.api import job_queue

    job_queue.enqueue(run_id="run_q4", tenant_id="t", filename="f.csv", content=b"x")
    job_queue.claim_next(worker_id="w")
    job_queue.mark_done("run_q4")
    assert job_queue.queue_depth().get("done") == 1


# --------------------------------------------------------------------------- #
# End-to-end: enqueue -> claim -> execute -> store (the worker's exact path,
# driven deterministically so there's no background-timing flakiness)
# --------------------------------------------------------------------------- #


def test_durable_job_executes_end_to_end(durable_db):
    from app.api import job_queue
    from app.api.runner import execute_job
    from app.api.store import get_store

    content = SAMPLE.read_bytes()
    job_queue.enqueue(
        run_id="run_e2e", tenant_id="t", filename="exception_queue.csv", content=content
    )

    # Exactly what RunWorker._run_job does: claim, execute_job, mark_done.
    claimed = job_queue.claim_next(worker_id="w1")
    assert claimed is not None and claimed.run_id == "run_e2e"
    store = get_store()
    final = execute_job(
        run_id=claimed.run_id,
        content=claimed.content,
        filename=claimed.filename,
        tenant_id=claimed.tenant_id,
        store=store,
    )
    assert str(final["status"]).endswith("AWAITING_REVIEW")
    job_queue.mark_done(claimed.run_id)
    assert job_queue.queue_depth().get("done") == 1

    # The completed run is durably readable from the DB-backed store.
    got = store.get("run_e2e")
    assert got is not None
    assert len(got["classifications"]) == 25


def test_submit_run_enqueues_in_durable_mode(durable_db):
    """POST-side: submit_run persists the input to the queue and returns PENDING
    without executing inline."""
    import asyncio

    from app.api import job_queue
    from app.api.runner import submit_run
    from app.api.store import get_store

    store = get_store()
    run_id = asyncio.run(
        submit_run(content=b"a,b\n1,2\n", filename="x.csv", tenant_id="t", store=store)
    )
    # Visible immediately as queued; nothing has executed yet.
    assert job_queue.queue_depth().get("queued") == 1
    state = store.get(run_id)
    assert state is not None
    assert str(state["status"]).endswith("PENDING")
