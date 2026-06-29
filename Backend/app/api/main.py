"""FastAPI entrypoint."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app.api.auth import require_auth
from app.api.middleware import (
    RequestContextMiddleware,
    RequestIdFilter,
    SecurityHeadersMiddleware,
    request_id_ctx,
)
from app.api.routes_analytics import router as analytics_router
from app.api.routes_comms import router as comms_router
from app.api.routes_config import router as config_router
from app.api.routes_contact import router as contact_router
from app.api.routes_db import router as db_router
from app.api.routes_metrics import router as metrics_router
from app.api.routes_notifications import router as notifications_router
from app.api.routes_oauth import router as oauth_router
from app.api.routes_org_integrations import router as integrations_router
from app.api.routes_preview import router as preview_router
from app.api.routes_review import router as review_router
from app.api.routes_rules import router as rules_router
from app.api.routes_runs import router as runs_router
from app.api.routes_upload import router as upload_router
from app.api.routes_vendor_contacts import router as vendor_contacts_router
from app.api.routes_vendors import router as vendors_router
from app.config import get_settings


async def _db_unavailable_handler(request: Request, exc: Exception) -> JSONResponse:
    """Turn a DB connectivity failure into a clean 503 instead of a raw 500.

    Catches the connection-class SQLAlchemy errors (host unreachable, refused,
    pool-checkout/timeout) that any DB-touching route can raise — so a paused
    Supabase / bad DATABASE_URL never leaks a stack trace to the client. Logic
    errors (IntegrityError, ProgrammingError, ...) are deliberately NOT caught
    here so they still surface as 500s in development."""
    rid = request_id_ctx.get()
    logging.getLogger("ap_agent").warning(
        "db unavailable on %s %s: %s", request.method, request.url.path, exc.__class__.__name__
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable (database error).", "request_id": rid},
        headers={"X-Request-ID": rid},
    )


def _configure_logging() -> None:
    settings = get_settings()
    level = settings.resolved_log_level
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-5s | %(name)-22s | %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    # Tame third-party noise but keep our own loggers at the configured level.
    # These SDKs dump enormous DEBUG payloads (full prompt + headers) — we
    # never want them at DEBUG, even when our pipeline loggers are.
    for noisy in (
        "httpx",
        "httpcore",
        "anthropic",
        "google_genai",
        "openai",
        "openai._base_client",
        "python_multipart",
        "python_multipart.multipart",
        "asyncio",
        "watchfiles",
    ):
        logging.getLogger(noisy).setLevel(max(level, logging.INFO))
    # httpcore is particularly chatty; pin it to WARNING regardless.
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Add the request-id to the format + attach the filter to the root handlers.
    fmt = "%(asctime)s | %(levelname)-5s | %(name)-22s | rid=%(request_id)s | %(message)s"
    rid_filter = RequestIdFilter()
    for h in logging.getLogger().handlers:
        h.setFormatter(logging.Formatter(fmt, datefmt="%H:%M:%S"))
        h.addFilter(rid_filter)


def _init_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.environment,
            traces_sample_rate=settings.sentry_traces_sample_rate,
        )
        logging.getLogger("ap_agent").info("Sentry initialized (env=%s)", settings.environment)
    except Exception:
        logging.getLogger("ap_agent").exception("Sentry init failed")


_configure_logging()
_init_sentry()


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # --- startup --- #
    if get_settings().run_queue_enabled:
        try:
            from app.api.worker import start_worker
            from app.db.session import init_db

            init_db()  # ensure run_jobs (+ schema) exists when using the queue
            await start_worker()
        except Exception:  # noqa: BLE001 — log, don't block startup of the API
            logging.getLogger("ap_agent").exception("run worker failed to start")
    yield
    # --- shutdown: stop the worker, then drain any legacy in-process runs --- #
    try:
        from app.api.worker import stop_worker

        await stop_worker()
    except Exception:  # noqa: BLE001 — shutdown must never raise
        logging.getLogger("ap_agent").exception("error stopping run worker on shutdown")
    try:
        from app.api.runner import drain_background_tasks

        await drain_background_tasks(timeout=get_settings().shutdown_drain_seconds)
    except Exception:  # noqa: BLE001 — shutdown must never raise
        logging.getLogger("ap_agent").exception("error draining background tasks on shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title="AP Exception Handling Agent",
        version="0.1.0",
        description=(
            "LangGraph-orchestrated workflow with selective Claude AI nodes "
            "for AP exception triage, classification, routing, comms drafting, "
            "and priority queue generation."
        ),
        lifespan=_lifespan,
    )
    settings = get_settings()

    # --- Fail fast on insecure production configuration ----------------- #
    # Matched by prefix (prod*/stag*) so a suffix typo can't downgrade security.
    if settings.is_protected_env:
        problems = []
        if not settings.auth_enabled:
            problems.append("AUTH_ENABLED must be true")
        if not settings.comms_dryrun and not settings.comms_allowed_domains_list:
            problems.append("set COMMS_ALLOWED_DOMAINS before enabling live sends")
        if not settings.cors_origins_list:
            problems.append("CORS_ALLOW_ORIGINS must be an explicit allow-list")
        if settings.run_store_backend == "memory":
            problems.append("RUN_STORE_BACKEND=memory loses runs on restart; use db/supabase")
        if not settings.run_queue_enabled:
            problems.append(
                "RUN_QUEUE_ENABLED must be true; fire-and-forget runs are lost on "
                "restart/deploy (no durable execution)"
            )
        # The Supabase REST store's send-claim is only best-effort (no row lock),
        # so concurrent sends across replicas can double-fire. Require the DB
        # store, whose claim takes a real SELECT ... FOR UPDATE lock.
        from app.api.store import _resolve_backend

        if _resolve_backend(settings) == "supabase":
            problems.append(
                "RUN_STORE_BACKEND resolves to 'supabase', whose send-claim is not "
                "atomic across replicas; use the DB store (db / DB_PERSISTENCE_ENABLED) "
                "in production"
            )
        if problems:
            raise RuntimeError("Insecure production config: " + "; ".join(problems))

    # --- Rate limiting (slowapi) ---------------------------------------- #
    if settings.rate_limit_enabled:
        from slowapi import Limiter, _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
        from slowapi.util import get_remote_address

        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=[settings.rate_limit_default],
        )
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(SlowAPIMiddleware)

    # --- DB-unavailable -> 503 (not a raw 500) -------------------------- #
    # Any route that touches the store/DB can raise a connection-class error;
    # handle it once here so a DB outage degrades cleanly everywhere.
    app.add_exception_handler(OperationalError, _db_unavailable_handler)
    app.add_exception_handler(InterfaceError, _db_unavailable_handler)

    # --- Security headers + request id ---------------------------------- #
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)

    # --- CORS ----------------------------------------------------------- #
    # Production: set CORS_ALLOW_ORIGINS to the exact frontend origin(s).
    # Dev (empty): permissive localhost/127.0.0.1 regex for the Vite console.
    if settings.cors_origins_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins_list,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # --- Routers (all /v1/* gated by Clerk JWT when AUTH_ENABLED) ------- #
    auth = [Depends(require_auth)]
    app.include_router(runs_router, dependencies=auth)
    app.include_router(upload_router, dependencies=auth)
    app.include_router(review_router, dependencies=auth)
    app.include_router(preview_router, dependencies=auth)
    app.include_router(integrations_router, dependencies=auth)
    app.include_router(rules_router, dependencies=auth)
    app.include_router(oauth_router, dependencies=auth)
    app.include_router(metrics_router, dependencies=auth)
    app.include_router(analytics_router, dependencies=auth)
    app.include_router(vendors_router, dependencies=auth)
    app.include_router(vendor_contacts_router, dependencies=auth)
    app.include_router(comms_router, dependencies=auth)
    app.include_router(notifications_router, dependencies=auth)
    app.include_router(config_router, dependencies=auth)
    app.include_router(db_router, dependencies=auth)
    # Public (no auth): the landing-page contact form + newsletter signup.
    app.include_router(contact_router)

    # Ensure the normalized schema exists at startup when enabled.
    if get_settings().db_persistence_enabled:
        try:
            from app.db.session import init_db

            init_db()
        except Exception:
            logging.getLogger("ap_agent").exception("init_db failed at startup")

    @app.get("/")
    def index() -> dict:
        return {
            "service": "ap-exception-agent",
            "version": "0.1.0",
            "docs": "/docs",
            "openapi": "/openapi.json",
            "health": "/healthz",
            "endpoints": {
                "create_run": "POST /v1/runs",
                "get_run": "GET /v1/runs/{run_id}",
                "results": "GET /v1/runs/{run_id}/results",
                "metrics": "GET /v1/runs/{run_id}/metrics",
                "audit": "GET /v1/runs/{run_id}/audit",
                "get_draft": "GET /v1/runs/{run_id}/drafts/{invoice_id}",
                "edit_draft": "PATCH /v1/runs/{run_id}/drafts/{invoice_id}",
                "approve": "POST /v1/runs/{run_id}/approve",
                "list_vendors": "GET /v1/vendors",
                "get_vendor": "GET /v1/vendors/{vendor_name}",
                "send_draft": "POST /v1/runs/{run_id}/drafts/{invoice_id}/send",
                "send_all": "POST /v1/runs/{run_id}/drafts/send_all",
                "list_sent": "GET /v1/runs/{run_id}/sent",
            },
        }

    @app.get("/healthz")
    def healthz() -> dict:
        """Liveness — the process is up and serving. No dependency checks."""
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> Response:
        """Prometheus text-exposition metrics (runs, AI tokens/cost, comms)."""
        from app.observability import render_prometheus

        return Response(content=render_prometheus(), media_type="text/plain; version=0.0.4")

    @app.get("/readyz")
    def readyz(response: Response) -> dict:
        """Readiness — verifies the app can actually serve traffic by probing
        its hard dependencies (the run store, and the DB when normalized
        persistence is on). Returns 503 if anything is unreachable so an
        orchestrator won't route traffic to a half-initialized instance.
        """
        checks: dict[str, str] = {}
        ok = True

        from app.api.store import get_store

        try:
            store = get_store()
            store.ping()
            checks["run_store"] = f"ok:{getattr(store, 'backend_name', 'unknown')}"
        except Exception as e:  # noqa: BLE001 — report, don't crash the probe
            ok = False
            checks["run_store"] = f"error:{type(e).__name__}"
            logging.getLogger("ap_agent").warning("readyz: run store probe failed: %s", e)

        if settings.db_persistence_enabled:
            try:
                from sqlalchemy import text

                from app.db.session import get_engine

                with get_engine().connect() as conn:
                    conn.execute(text("SELECT 1"))
                checks["db"] = "ok"
            except Exception as e:  # noqa: BLE001
                ok = False
                checks["db"] = f"error:{type(e).__name__}"
                logging.getLogger("ap_agent").warning("readyz: db probe failed: %s", e)

        if not ok:
            response.status_code = 503
        return {"status": "ready" if ok else "not_ready", "checks": checks}

    return app


app = create_app()
