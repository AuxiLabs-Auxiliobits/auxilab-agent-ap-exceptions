"""Application configuration."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# Point APP_ENV_FILE at an out-of-repo secrets file (e.g. .env.prod) to load
# it instead of the default local .env. Unset => fall back to ".env" in the
# current working directory.
_ENV_FILE = os.environ.get("APP_ENV_FILE", ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ap-exception-agent"
    environment: str = "dev"
    log_level: str = "INFO"

    # Environments that must enforce the production safety gates (auth, CORS
    # allow-list, comms allow-list, durable store). Matched by prefix so
    # "production-us-west", "staging-2", "PROD" etc. are all covered — a typo
    # in the suffix can't silently downgrade security.
    _PROTECTED_ENV_PREFIXES: ClassVar[tuple[str, ...]] = ("prod", "stag")

    @property
    def is_protected_env(self) -> bool:
        return self.environment.strip().lower().startswith(self._PROTECTED_ENV_PREFIXES)

    @property
    def resolved_log_level(self) -> int:
        """Map LOG_LEVEL → logging constant, rejecting typos loudly so a
        misconfigured level (e.g. 'DEBGU') can't silently fall back to INFO."""
        import logging as _logging

        name = self.log_level.strip().upper()
        level = _logging.getLevelName(name)
        if not isinstance(level, int):
            raise ValueError(
                f"Invalid LOG_LEVEL {self.log_level!r}; expected one of "
                "DEBUG, INFO, WARNING, ERROR, CRITICAL."
            )
        return level

    # ------------------------------------------------------------------ #
    # API authentication (Clerk JWT). Opt-in: when AUTH_ENABLED=true every
    # /v1/* route requires a valid Clerk session token (Bearer).          #
    # ------------------------------------------------------------------ #
    auth_enabled: bool = False
    clerk_issuer: str = Field(default="", description="Clerk issuer, e.g. https://xxx.clerk.accounts.dev")
    clerk_jwks_url: str = Field(default="", description="Override JWKS URL (else derived from issuer)")
    clerk_audience: str = Field(default="", description="Optional audience/azp to enforce")
    # RBAC fallback role: applied to an authenticated caller whose token carries
    # no recognizable role (no app-role claim and no mapped Clerk org role).
    # `org:admin` always maps to admin regardless of this. Tighten/loosen per
    # deployment; see app/api/roles.py for the role → permission matrix.
    auth_default_role: str = Field(
        default="clerk",
        description="Role for an authenticated caller with no role claim (one of: "
        "admin, manager, clerk, controller, auditor, procurement)",
    )

    # ------------------------------------------------------------------ #
    # Per-org integrations (Phase 2 — BYOK). When enabled, an org's stored #
    # config (its own AI provider key/model) overrides the env defaults at #
    # run time, resolved per run from the caller's tenant. Storing secrets  #
    # requires CONFIG_ENC_KEY (they are encrypted at rest, never returned). #
    # Default OFF → behaviour is unchanged (env is the single config).      #
    # ------------------------------------------------------------------ #
    per_org_config_enabled: bool = False
    config_enc_key: str = Field(
        default="",
        description="Fernet key (urlsafe base64, 32 bytes) used to encrypt per-org "
        "integration secrets. Generate: "
        'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"',
    )

    # ---- OAuth apps (platform-level; orgs authorize against these) ---- #
    # Gmail "send as the org" via OAuth. Register a Google Cloud OAuth client
    # (scope gmail.send) and set these; the redirect URI is a frontend route.
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = ""  # e.g. https://app.example.com/integrations/google/callback
    # Slack app install (chat:write). Register a Slack app and set these.
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_redirect_uri: str = ""
    slack_default_channel: str = ""  # fallback channel id/name if an org doesn't pick one

    # Runtime-only (NOT read from env): populated per-run by org_config.resolve_settings
    # from a tenant's OAuth integration. Kept here so the dispatcher reads them
    # uniformly alongside the SMTP/webhook fields.
    gmail_oauth_refresh_token: str = ""
    slack_bot_token: str = ""
    slack_channel: str = ""

    @property
    def jwks_url(self) -> str:
        if self.clerk_jwks_url:
            return self.clerk_jwks_url
        if self.clerk_issuer:
            return self.clerk_issuer.rstrip("/") + "/.well-known/jwks.json"
        return ""

    # ------------------------------------------------------------------ #
    # CORS / security headers                                            #
    # ------------------------------------------------------------------ #
    # Comma-separated exact origins for production. Empty => permissive
    # localhost-only regex (dev).
    cors_allow_origins: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    # ------------------------------------------------------------------ #
    # Rate limiting (slowapi)                                            #
    # ------------------------------------------------------------------ #
    rate_limit_enabled: bool = True
    rate_limit_default: str = "240/minute"

    # ------------------------------------------------------------------ #
    # Observability                                                      #
    # ------------------------------------------------------------------ #
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0

    # Anthropic (preferred provider)
    anthropic_api_key: str = Field(default="", description="Anthropic API key")
    classify_model: str = "claude-opus-4-7"
    draft_model: str = "claude-sonnet-4-6"
    # "Ask the desk" hybrid assistant: understands the question + phrases
    # grounded answers (numbers stay deterministic). Sonnet balances latency and
    # quality for an interactive chat widget; bump to claude-opus-4-8 for the
    # most capable answers.
    assistant_model: str = "claude-sonnet-4-6"

    # Gemini (fallback #1, used when ANTHROPIC_API_KEY is empty)
    gemini_api_key: str = Field(
        default="",
        description="Google Gemini API key (used as fallback when Anthropic key is missing)",
    )
    # NOTE: defaults are both Flash because gemini-2.5-pro has a 0 RPM free
    # tier — every request 429s. Override to Pro in .env only if you have a
    # paid Gemini key.
    gemini_classify_model: str = "gemini-2.5-flash"
    gemini_draft_model: str = "gemini-2.5-flash"

    # Azure OpenAI (fallback #2, used when both Anthropic and Gemini keys are empty)
    azure_openai_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_chat_openai_endpoint: str = Field(
        default="",
        description="Azure OpenAI resource endpoint, e.g. https://<resource>.openai.azure.com/",
    )
    azure_openai_deployment: str = Field(
        default="gpt-4o-mini",
        description="Azure OpenAI deployment name (treated as the model id)",
    )
    azure_openai_version: str = Field(
        default="2024-10-21",
        description="Azure OpenAI API version",
    )

    ai_max_retries: int = 4
    ai_timeout_seconds: int = 60
    ai_max_concurrency: int = 10
    classify_batch_size: int = 20

    # Per-task wall-clock ceiling for a single classify/draft AI call. Bounds a
    # hung provider response so one stuck row can't stall the whole run.
    ai_task_timeout_seconds: int = 45

    # On shutdown (SIGTERM/deploy), wait this long for in-flight background runs
    # to reach a terminal status before the process exits.
    shutdown_drain_seconds: int = 30

    # Explicit provider selection. Empty (default) => auto-detect by precedence,
    # which is the historical behaviour. Set to pin one provider so a key left
    # configured for a higher-precedence provider can't silently win — e.g.
    # AI_PROVIDER=gemini is honoured even when ANTHROPIC_API_KEY is also set.
    ai_provider: str = Field(
        default="",
        description="Force an AI provider (anthropic|gemini|azure|mock). "
        "Empty => auto precedence: anthropic > gemini > azure > mock.",
    )

    _VALID_AI_PROVIDERS: ClassVar[tuple[str, ...]] = ("anthropic", "gemini", "azure", "mock")

    @property
    def _provider_ready(self) -> dict[str, bool]:
        """Which providers have enough config to actually be constructed."""
        return {
            "anthropic": bool(self.anthropic_api_key),
            "gemini": bool(self.gemini_api_key),
            "azure": bool(self.azure_openai_api_key and self.azure_chat_openai_endpoint),
            "mock": True,
        }

    @property
    def active_ai_provider(self) -> str:
        """The provider to run with.

        An explicit AI_PROVIDER wins outright. If that provider is missing its
        credentials we fall back to mock rather than sliding to a *different*
        live provider — silently billing a provider the operator didn't pick
        would be worse than running the deterministic offline path.
        """
        ready = self._provider_ready
        forced = self.ai_provider.strip().lower()
        if forced:
            if forced not in self._VALID_AI_PROVIDERS:
                raise ValueError(
                    f"Invalid AI_PROVIDER {self.ai_provider!r}; expected one of "
                    + ", ".join(self._VALID_AI_PROVIDERS)
                )
            return forced if ready[forced] else "mock"

        # No explicit choice: auto precedence (unchanged).
        for name in ("anthropic", "gemini", "azure"):
            if ready[name]:
                return name
        return "mock"

    def model_for(self, purpose: str) -> str:
        """Resolve the model id to use for a given node purpose under the active provider.

        Azure: a single deployment is used for both classify and draft, since
        each deployment is itself a pinned model on the resource. Provision
        separate deployments and split here if you need different models.
        """
        provider = self.active_ai_provider
        if provider == "anthropic":
            if purpose == "assistant":
                return self.assistant_model
            return self.classify_model if purpose == "classify" else self.draft_model
        if provider == "gemini":
            # The managed Flash model serves every purpose on the Gemini fallback.
            return (
                self.gemini_classify_model
                if purpose == "classify"
                else self.gemini_draft_model
            )
        if provider == "azure":
            return self.azure_openai_deployment
        return f"mock-{purpose}"

    # Persistence
    database_url: str = "sqlite+pysqlite:///./ap_agent.db"
    artifact_dir: Path = Path("./artifacts")

    # Normalized enterprise persistence (SQLAlchemy). When True, each completed
    # run is written into the normalized tables (exceptions, classifications,
    # resolutions, communications, status_history, agent_executions, priorities,
    # vendors) in addition to the run store. Uses `database_url` (sqlite by
    # default; set to a Postgres/Supabase URL for production).
    db_persistence_enabled: bool = False

    # Supabase-backed run store. When SUPABASE_URL + SUPABASE_KEY are both set,
    # the run store persists to a Supabase `runs` table (durable across
    # restarts); otherwise it falls back to the in-memory store.
    # NOTE: use the SERVICE_ROLE key on the backend (bypasses RLS), not the
    # publishable/anon key.
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_key: str = Field(default="", description="Supabase service_role key (server-side)")
    supabase_runs_table: str = "runs"

    # Run-store backend selection (the operational store the API reads/writes).
    #   auto     — DB store when DB_PERSISTENCE_ENABLED (uses DATABASE_URL),
    #              else Supabase REST when SUPABASE_URL/KEY set, else in-memory.
    #   db       — force the SQLAlchemy/DATABASE_URL store.
    #   supabase — force the Supabase REST store.
    #   memory   — force the in-memory store (no durability).
    run_store_backend: str = "auto"

    # ------------------------------------------------------------------ #
    # Durable run-execution queue (DB-backed). When enabled, an uploaded   #
    # run's input is persisted to the run_jobs table and a worker executes #
    # it — so a run survives a restart and a crashed run is re-leased and   #
    # retried. Requires a DB (DATABASE_URL). When OFF (default), runs       #
    # execute as in-process background tasks (not durable across restarts). #
    # ------------------------------------------------------------------ #
    run_queue_enabled: bool = False
    run_queue_poll_seconds: float = 0.25
    run_queue_lease_seconds: int = 300
    run_queue_concurrency: int = 2
    run_queue_max_attempts: int = 3
    # Exponential retry backoff base: after a failed attempt a job is held
    # un-claimable for base * 2**(attempt-1) seconds (capped at 5 min), so a
    # job that fails instantly doesn't burn all its attempts in a fraction of a
    # second of tight polling. 0 disables backoff (retry immediately).
    run_queue_retry_backoff_seconds: float = 5.0

    # Rules engine
    rules_policy_path: Path = Path("app/rules/policies/default.yaml")
    # Materiality guardrail: an invoice at/above this amount can NEVER auto-approve,
    # regardless of what the policy rules say — a hard backstop against a
    # mis-calibrated or too-lenient AUTO_APPROVE rule. Such an invoice is routed to
    # MANUAL_REVIEW instead, with the override recorded in the rule trace. Set to 0
    # to disable the guard (trust the policy alone).
    auto_approve_max_amount: float = 10_000

    # Vendor reliability sidecar — longitudinal per-vendor history is
    # persisted to this JSON file. Profiles enrich the classifier prompt
    # on subsequent runs.
    vendor_profiles_path: Path = Path("artifacts/vendor_profiles.json")
    vendor_history_enabled: bool = True

    # -------------------------------------------------------------- #
    # Outbound communications (email + Slack)                         #
    # -------------------------------------------------------------- #
    # When ON, sends write .eml / .json files to artifacts/sent/{run_id}/
    # instead of hitting Gmail or Slack. This is the default until the
    # operator explicitly flips COMMS_DRYRUN=false.
    comms_dryrun: bool = True
    comms_sent_dir: Path = Path("artifacts/sent")

    # Gmail SMTP (requires 2FA + App Password — NOT your regular password)
    gmail_smtp_host: str = "smtp.gmail.com"
    gmail_smtp_port: int = 587
    gmail_smtp_user: str = Field(default="", description="Gmail address used as From:")
    gmail_smtp_password: str = Field(
        default="", description="Gmail App Password (16 chars, no spaces)"
    )

    # Slack Incoming Webhook URL — single channel
    slack_webhook_url: str = Field(default="", description="Slack incoming webhook URL")

    # Default test recipient (until vendor master integration ships). No
    # hardcoded default — set COMMS_TEST_RECIPIENT in .env. Empty => the
    # resolver refuses to send (draft is SKIPPED) rather than silently routing
    # every email to one person's inbox.
    comms_test_recipient: str = ""
    # AP team mailbox — vendors' Reply-To, and the BCC for every outbound mail
    # so the human team has a copy of everything the agent sent.
    comms_ap_team_mailbox: str = ""
    # Finance Controller mailbox — destination for FINANCE_NOTE channel when
    # Slack isn't configured. If empty, falls back to comms_ap_team_mailbox.
    comms_finance_controller_mailbox: str = ""

    # Vendor master CSV (vendor_name -> email). When set, the recipient resolver
    # looks up the real vendor AR contact for VENDOR_EMAIL drafts instead of
    # routing to the test recipient. Empty => fall back to COMMS_TEST_RECIPIENT.
    vendor_master_path: Path | None = None

    # Per-domain throttle to prevent runaway escalation storms.
    comms_per_domain_daily_cap: int = 25

    # How long a draft may sit in the in-flight SENDING state before its claim is
    # considered stale and re-claimable. Bounds the window in which a process
    # killed mid-send leaves a draft wedged; must exceed a real send's duration
    # (seconds) but be short enough to recover quickly.
    comms_send_claim_ttl_seconds: float = 120.0

    # SLA visibility (F1-2): an item whose resolution deadline is within this many
    # hours is flagged "due soon" in the operator SLA report/digest.
    comms_sla_due_soon_hours: float = 4.0

    # Live-send safety allowlist: comma-separated recipient domains permitted
    # for REAL (non-dry-run) sends. Empty => allow all (back-compat). Set this
    # in production so a bad run can't email arbitrary vendor domains.
    comms_allowed_domains: str = ""

    @property
    def comms_allowed_domains_list(self) -> list[str]:
        return [d.strip().lower().lstrip("@") for d in self.comms_allowed_domains.split(",") if d.strip()]

    # ---- Email rendering ----
    # Send HTML + plain text (multipart/alternative). Set to false to fall
    # back to plain text only (some compliance regimes prefer that).
    comms_email_html_enabled: bool = True
    # Consolidated emails covering MORE than this many invoices send a short body
    # plus a spreadsheet (.xlsx) attachment of the full list, instead of inlining
    # a section per invoice (which becomes an unreadable wall of text). Set to a
    # very large number to always inline, or 0 to always attach.
    comms_consolidated_attachment_threshold: int = 10
    # Signature block appended to every outbound email (NOT generated by the
    # LLM — added deterministically at send time so it's consistent).
    comms_signature_name: str = "AP Operations Team"
    comms_signature_team: str = "Accounts Payable"
    comms_signature_company: str = "Auxiliobits"
    comms_signature_disclaimer: str = (
        "This message is confidential and intended for the addressee only. "
        "If received in error, please notify the sender and delete."
    )
    # When true, adds a small "Prepared by AP Exception Agent and reviewed
    # by the AP team" line in the footer. Some clients prefer this for
    # transparency; leave off if you want the agent invisible.
    comms_disclose_ai_assistance: bool = False

    # Brand customization for outbound email (settable per-org via the Branding
    # integration). brand_color overrides the channel header bar; logo_url, if set,
    # renders a small logo in the header.
    comms_brand_color: str = ""
    comms_logo_url: str = ""

    # ---- Public contact / newsletter (landing page) ----
    # Where website "Contact us" + newsletter submissions are emailed. Falls back
    # to the SMTP sender, then the AP team mailbox.
    contact_recipient: str = ""
    # Contact/newsletter mail only ever goes to your OWN inbox, so it is sent by
    # default — independent of COMMS_DRYRUN (which exists to prevent accidental
    # *vendor* sends). Set CONTACT_DRYRUN=true to log instead of send (dev).
    contact_dryrun: bool = False

    @property
    def contact_to(self) -> str:
        return self.contact_recipient or self.gmail_smtp_user or self.comms_ap_team_mailbox

    # ---- Newsletter / subscribers (platform marketing) ----
    # Token that protects POST /v1/newsletter (the bulk send). Empty => the
    # endpoint is disabled (use the scripts/send_newsletter.py CLI instead).
    newsletter_admin_token: str = ""
    # Cap recipients per newsletter send (Gmail daily-limit throttle guard).
    newsletter_max_per_send: int = 500
    # Absolute base URL used to build unsubscribe links in emails (no trailing
    # slash), e.g. https://app.example.com. Falls back to the local API.
    public_base_url: str = ""

    @property
    def unsubscribe_base(self) -> str:
        return (self.public_base_url or "http://localhost:8000").rstrip("/")

    # Priority scoring weights
    w_amount: float = 0.30
    w_age: float = 0.25
    w_severity: float = 0.25
    w_path: float = 0.15
    w_conf: float = 0.05

    high_threshold: float = 0.70
    medium_threshold: float = 0.40

    # Severity thresholds (deterministic)
    severity_high_amount: float = 25_000
    severity_high_days: int = 30
    severity_medium_amount_min: float = 5_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
