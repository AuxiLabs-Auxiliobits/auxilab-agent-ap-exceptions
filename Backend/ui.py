#!/usr/bin/env python
"""AP Exception Handling agent — Gradio interface.

One command, one browser tab, no login:

    python ui.py          # run once
    gradio ui.py          # run with hot reload (auto-restarts on edits)

Upload a CSV of invoice exceptions (or click "Load sample") and the agent
ingests, classifies, routes, and drafts communications for the whole queue,
then shows KPIs, a per-invoice table, the drafted messages, rejected rows, and
a downloadable JSON report.

Runs fully offline in deterministic mock mode when no AI provider key is set
(see .env.example). Set ANTHROPIC_API_KEY to use real Claude classification.
"""
from __future__ import annotations

import html
import json
import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path

import gradio as gr

from app.config import get_settings
from app.standalone import ai_mode, build_report, run_pipeline_path

SAMPLE_CSV = Path(__file__).parent / "examples" / "sample_exceptions.csv"

# --------------------------------------------------------------------------- #
# Theme-aware CSS (uses Gradio CSS vars so it adapts to light/dark)            #
# --------------------------------------------------------------------------- #
CSS = """
/* ---- App header: brand | mode pill | settings button --------------------- */
.app-header { align-items: center; gap: 12px; }
.brand { display: flex; align-items: center; gap: 14px; }
.brand .logo { width: 46px; height: 46px; flex: 0 0 46px; border-radius: 11px;
    display: grid; place-items: center; font-size: 1.5rem;
    background: linear-gradient(135deg, #4f46e5, #2563eb); }
.brand h1 { margin: 0; font-size: 1.5rem; line-height: 1.2; font-weight: 700; }
.brand p { margin: 3px 0 0; font-size: .85rem; opacity: .7; line-height: 1.35; }
.mode-pill { border: 1px solid var(--border-color-primary); border-radius: 10px;
    padding: 7px 14px; text-align: center; background: var(--background-fill-secondary); }
.mode-pill .t { font-weight: 600; font-size: .92rem; white-space: nowrap; }
.mode-pill .s { font-size: .72rem; opacity: .65; margin-top: 1px; white-space: nowrap; }
.mode-pill.is-mock .t { color: #16a34a; }
.mode-pill.is-live .t { color: #2563eb; }

/* ---- Settings modal: a Column promoted to a fixed overlay ----------------- */
/* Visibility is driven by the modal-open / modal-closed class, NOT Gradio's
   `visible=` flag. An earlier version used `visible=` plus `display: flex
   !important`, and the !important beat Gradio's own hiding rule — so closing
   the modal left the dimmed backdrop covering the page until a full reload.
   Owning both states here means nothing can be overridden out from under us. */
.modal-closed { display: none !important; }
.modal-wrap.modal-open { position: fixed; inset: 0; z-index: 1000;
    background: rgba(0,0,0,.55); backdrop-filter: blur(2px);
    display: flex; align-items: center; justify-content: center; padding: 20px; }
.modal-card { width: min(680px, 94vw); max-height: 86vh; overflow-y: auto;
    background: var(--background-fill-primary); border: 1px solid var(--border-color-primary);
    border-radius: 14px; padding: 4px 22px 18px; box-shadow: 0 24px 64px rgba(0,0,0,.5); }
.modal-card h3 { margin-top: 14px; }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px; margin: 4px 0 8px; }
.kpi { border: 1px solid var(--border-color-primary); border-radius: var(--block-radius, 8px);
       padding: 14px 16px; background: var(--background-fill-secondary); }
.kpi .val { font-size: 1.7rem; font-weight: 700; line-height: 1.1; }
.kpi .lbl { font-size: .8rem; opacity: .7; margin-top: 4px; }
.kpi.accent-red    .val { color: #dc2626; }
.kpi.accent-amber  .val { color: #d97706; }
.kpi.accent-green  .val { color: #16a34a; }
.kpi.accent-blue   .val { color: #2563eb; }
.bd-wrap { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
.bd h4 { margin: 6px 0; font-size: .95rem; }
.bd-row { display: flex; justify-content: space-between; padding: 3px 0;
          border-bottom: 1px dashed var(--border-color-primary); font-size: .9rem; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: .72rem;
         font-weight: 600; }
.badge.HIGH   { background: rgba(220,38,38,.15);  color: #dc2626; }
.badge.MEDIUM { background: rgba(217,119,6,.15);  color: #d97706; }
.badge.LOW    { background: rgba(22,163,74,.15);  color: #16a34a; }
.draft { border: 1px solid var(--border-color-primary); border-radius: 8px;
         padding: 12px 14px; margin-bottom: 12px; background: var(--background-fill-secondary); }
.draft .meta { font-size: .78rem; opacity: .75; margin-bottom: 6px; }
.draft .subj { font-weight: 600; margin-bottom: 6px; }
.draft .body { white-space: pre-wrap; font-size: .9rem; line-height: 1.45; }
.chip { display:inline-block; padding:1px 8px; border-radius:6px; font-size:.72rem;
        background: var(--background-fill-primary); border:1px solid var(--border-color-primary); }
.status-line { font-size:.9rem; padding:10px 14px; border-radius:8px;
               border:1px solid var(--border-color-primary); background: var(--background-fill-secondary); }
/* Fixed-height, scrollable JSON viewer (fallback if max_lines is ignored). */
.json-report .cm-scroller, .json-report .cm-editor { max-height: 460px; overflow: auto; }
.json-report { max-height: 500px; overflow: auto; }
/* Fixed-height, scrollable Communications panel. */
.drafts-panel { max-height: 560px; overflow-y: auto; padding-right: 6px; }
/* Theme-matched scrollbar (default OS bar renders bright/white on the dark editor). */
.dark-scroll, .dark-scroll * { scrollbar-width: thin;
    scrollbar-color: var(--border-color-accent, #4b5563) transparent; }
.dark-scroll ::-webkit-scrollbar, .dark-scroll::-webkit-scrollbar { width: 11px; height: 11px; }
.dark-scroll ::-webkit-scrollbar-track, .dark-scroll::-webkit-scrollbar-track { background: transparent; }
.dark-scroll ::-webkit-scrollbar-thumb, .dark-scroll::-webkit-scrollbar-thumb {
    background: var(--border-color-accent, #4b5563); border-radius: 6px;
    border: 2px solid transparent; background-clip: content-box; }
.dark-scroll ::-webkit-scrollbar-thumb:hover, .dark-scroll::-webkit-scrollbar-thumb:hover {
    background: var(--body-text-color-subdued, #6b7280); background-clip: content-box; }
"""

TABLE_HEADERS = [
    "Invoice",
    "Vendor",
    "Amount",
    "Type",
    "Severity",
    "Recommended approach",
    "Priority",
    "Score",
    "Draft?",
]


# --------------------------------------------------------------------------- #
# Formatting helpers                                                           #
# --------------------------------------------------------------------------- #
def _abbrev_num(v) -> str:
    """Compact number: 950 -> '950', 12500 -> '12.5K', 3_400_000 -> '3.4M'."""
    try:
        n = float(v)
    except (ValueError, TypeError):
        return str(v)
    sign = "-" if n < 0 else ""
    n = abs(n)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if n >= div:
            s = f"{n / div:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{s}{suf}"
    return f"{sign}{int(n)}" if n == int(n) else f"{sign}{n:g}"


def _abbrev_money(v) -> str:
    """Compact currency: 320 -> '$320.00', 774450 -> '$774.5K'."""
    try:
        n = float(Decimal(str(v)))
    except (InvalidOperation, ValueError, TypeError):
        return str(v)
    if abs(n) >= 1000:
        return f"${_abbrev_num(n)}"
    return f"${n:,.2f}"


def _money(v) -> str:
    """Full currency (used in the per-invoice table): 182400 -> '$182,400.00'."""
    try:
        return f"${Decimal(str(v)):,.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return str(v)


def _badge(sev: str | None) -> str:
    sev = (sev or "").upper()
    if sev in ("HIGH", "MEDIUM", "LOW"):
        return f'<span class="badge {sev}">{sev}</span>'
    return html.escape(sev or "-")


BRAND_HTML = (
    # '<div class="brand"><div class="logo">🤖</div><div>'
    "<h1>AP Exception Handling Agent</h1>"
    "<p>Analyze AP invoice exception queues using AI and business rules to "
    "generate actionable insights and communications.</p>"
    "</div></div>"
)


def _mode_pill() -> str:
    """Compact provider indicator for the header."""
    mode = ai_mode()
    if mode == "mock":
        return (
            '<div class="mode-pill is-mock"><div class="t">✓ Mock Mode</div>'
            # '<div class="s">No API key required</div></div>'
        )
    label = (PROVIDERS.get(mode) or {}).get("label", mode)
    return (
        f'<div class="mode-pill is-live"><div class="t">● {html.escape(label)}</div>'
        # '<div class="s">Live AI provider</div></div>'
    )


def _mode_detail() -> str:
    """Fuller status line, shown inside the settings modal.

    The header pill sits behind the modal backdrop, so the modal needs its own
    copy of the current state — otherwise applying a provider gives no visible
    confirmation until the modal is closed.
    """
    mode = ai_mode()
    if mode == "mock":
        return (
            '<div class="status-line">🟢 <b>Offline mock mode</b> — no API key required. '
            "Deterministic output for the whole pipeline.</div>"
        )
    label = (PROVIDERS.get(mode) or {}).get("label", mode)
    return f'<div class="status-line">🔵 Live AI provider: <b>{html.escape(label)}</b></div>'


def _status_html(report: dict) -> str:
    return (
        '<div class="status-line">'
        f'<b>Run:</b> <code>{html.escape(str(report.get("run_id")))}</code> &nbsp;·&nbsp; '
        f'<b>Status:</b> {html.escape(str(report.get("status")).split(".")[-1])} &nbsp;·&nbsp; '
        f'<b>AI mode:</b> {html.escape(str(report.get("ai_mode")))}'
        "</div>"
    )


def _kpi_html(report: dict) -> str:
    m = report.get("summary") or {}
    cards = [
        ("blue", _abbrev_num(m.get("total_exceptions", 0)), "Total exceptions"),
        ("green", _abbrev_num(m.get("auto_resolvable_count", 0)), "Auto-resolvable"),
        ("red", _abbrev_num(m.get("escalations_required", 0)), "Need escalation"),
        ("amber", _abbrev_num(m.get("sla_at_risk_count", 0)), "SLA at risk"),
        ("blue", _abbrev_money(m.get("total_exception_value", 0)), "Total value"),
        ("blue", f'{m.get("average_confidence", 0):.0%}'
                 if isinstance(m.get("average_confidence"), (int, float)) else "-",
         "Avg AI confidence"),
        ("amber", _abbrev_num(len(report.get("quarantined", []))), "Rejected rows"),
    ]
    items = "".join(
        f'<div class="kpi accent-{c}"><div class="val">{html.escape(str(v))}</div>'
        f'<div class="lbl">{html.escape(l)}</div></div>'
        for c, v, l in cards
    )
    return f'<div class="kpi-grid">{items}</div>'


def _breakdown_html(report: dict) -> str:
    m = report.get("summary") or {}

    def block(title: str, d: dict, badge: bool = False) -> str:
        if not d:
            return ""
        rows = "".join(
            f'<div class="bd-row"><span>{_badge(k) if badge else html.escape(str(k))}</span>'
            f"<span>{html.escape(str(v))}</span></div>"
            for k, v in d.items()
        )
        return f'<div class="bd"><h4>{html.escape(title)}</h4>{rows}</div>'

    blocks = (
        block("By exception type", m.get("breakdown_by_type") or {})
        + block("By severity", m.get("breakdown_by_severity") or {}, badge=True)
        + block("By resolution path", m.get("breakdown_by_resolution_path") or {})
    )
    top = m.get("top_5_actionable") or []
    if top:
        rows = "".join(
            f'<div class="bd-row"><span>{html.escape(str(e.get("invoice_id")))} '
            f'{_badge(e.get("bucket"))}</span>'
            f'<span>score {e.get("priority_score")}</span></div>'
            for e in top
        )
        blocks += f'<div class="bd"><h4>Top actionable</h4>{rows}</div>'
    return f'<div class="bd-wrap">{blocks}</div>'


def _exceptions_rows(report: dict) -> list[list]:
    rows = []
    for e in report["exceptions"]:
        cls = e.get("classification") or {}
        res = e.get("resolution") or {}
        pr = e.get("priority") or {}
        rows.append(
            [
                e["invoice_id"],
                e["vendor_name"],
                _money(e["invoice_amount"]),
                cls.get("primary_type"),
                cls.get("severity"),
                res.get("recommended_approach"),
                (pr.get("bucket") or "").upper(),
                pr.get("score"),
                "Yes" if e["has_draft"] else "No",
            ]
        )
    return rows


def _drafts_html(report: dict) -> str:
    drafts = report.get("drafts", [])
    if not drafts:
        return "_No communications were drafted for this queue._"
    out = []
    for d in drafts:
        subj = html.escape(d.get("subject") or "(no subject)")
        body = html.escape(d.get("body") or "")
        recipient = html.escape(str(d.get("recipient_hint") or d.get("recipient") or "n/a"))
        out.append(
            '<div class="draft">'
            f'<div class="meta"><span class="chip">{html.escape(str(d.get("invoice_id")))}</span> '
            f'<span class="chip">{html.escape(str(d.get("channel")))}</span> '
            f"to: {recipient}</div>"
            f'<div class="subj">{subj}</div>'
            f'<div class="body">{body}</div>'
            "</div>"
        )
    return "".join(out)


def _quarantined_rows(report: dict) -> list[list]:
    rows = []
    for q in report.get("quarantined", []):
        rows.append(
            [
                q.get("row_index"),
                (q.get("raw") or {}).get("invoice_id", ""),
                q.get("reason_code"),
                q.get("reason"),
            ]
        )
    return rows


def _write_report_file(report: dict) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix="ap_report_", delete=False, encoding="utf-8"
    )
    json.dump(report, f, indent=2, default=str)
    f.close()
    return f.name


# --------------------------------------------------------------------------- #
# Callbacks                                                                    #
# --------------------------------------------------------------------------- #
_EMPTY = ("", "", "", [], "", [], "{}", None)


def process(file_obj):
    if file_obj is None:
        raise gr.Error("Please upload a CSV file, or click 'Load sample' first.")

    state = run_pipeline_path(file_obj.name)
    report = build_report(state)

    return (
        _status_html(report),
        _kpi_html(report),
        _breakdown_html(report),
        _exceptions_rows(report),
        _drafts_html(report),
        _quarantined_rows(report),
        json.dumps(report, indent=2, default=str),
        _write_report_file(report),
    )


def load_sample():
    return str(SAMPLE_CSV)


# ---- Runtime configuration (no restart) ----------------------------------- #
# Two ways to change the AI provider while the server is running. Both work by
# clearing the settings cache: get_settings is @lru_cache'd and ClaudeClient
# reads it per-construction, so writing an env var alone is NOT enough — the
# cached Settings would keep serving the old value with no error.
#
# Note there is no python-dotenv here and none is needed: pydantic-settings
# reads the .env file itself at instantiation, so cache_clear() alone re-reads
# it from disk.
#
# Precedence: os.environ beats the .env file, so a key typed into the UI shadows
# the file until "Reload from .env" drops it (see _forget_ui_key).

# Keys this UI injected into os.environ, so a reload can undo them without
# clobbering a value that came from the real shell environment.
_UI_INJECTED: set[str] = set()


def _forget_ui_keys() -> None:
    """Drop every UI-typed override so the .env file becomes authoritative again."""
    for name in list(_UI_INJECTED):
        os.environ.pop(name, None)
    _UI_INJECTED.clear()


def _set_env(name: str, value: str) -> None:
    """Record and apply a UI-typed env override (blank value => leave as-is)."""
    if value:
        os.environ[name] = value
        _UI_INJECTED.add(name)


# Provider registry. `model_envs` are the settings a chosen model is written to
# — the pipeline uses a separate model per purpose (classify / draft), and this
# UI sets one model for both rather than exposing two boxes. `models` seeds the
# dropdown; it stays editable so a newly released id can be typed in.
PROVIDERS: dict[str, dict] = {
    "mock": {"label": "Mock (offline, no key)", "key_env": "", "key_label": "",
             "models": [], "model_envs": ()},
    "anthropic": {
        "label": "Anthropic (Claude)",
        "key_env": "ANTHROPIC_API_KEY",
        "key_label": "ANTHROPIC_API_KEY",
        "placeholder": "sk-ant-...",
        "models": [
            "claude-opus-4-8",
            "claude-opus-4-7",
            "claude-sonnet-5",
            "claude-sonnet-4-6",
            "claude-haiku-4-5",
        ],
        "model_envs": ("CLASSIFY_MODEL", "DRAFT_MODEL"),
    },
    "gemini": {
        "label": "Google Gemini",
        "key_env": "GEMINI_API_KEY",
        "key_label": "GEMINI_API_KEY",
        "placeholder": "AIza...",
        # gemini-2.5-pro has a 0 RPM free tier (see app/config.py) — Flash first.
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "model_envs": ("GEMINI_CLASSIFY_MODEL", "GEMINI_DRAFT_MODEL"),
    },
    "azure": {
        "label": "Azure OpenAI",
        "key_env": "AZURE_OPENAI_API_KEY",
        "key_label": "AZURE_OPENAI_API_KEY",
        "placeholder": "azure resource key",
        # On Azure the "model" is your own deployment name, so these are only
        # examples — the dropdown is free-text for exactly this reason.
        "models": ["gpt-4o-mini", "gpt-4o"],
        "model_envs": ("AZURE_OPENAI_DEPLOYMENT",),
    },
}
PROVIDER_CHOICES = [(v["label"], k) for k, v in PROVIDERS.items()]


# Modal visibility is a class swap, not Gradio's `visible=` flag — see the
# .modal-closed / .modal-open note in CSS for why.
MODAL_OPEN = gr.update(elem_classes=["modal-wrap", "modal-open"])
MODAL_CLOSED = gr.update(elem_classes=["modal-wrap", "modal-closed"])


def _model_label(provider: str) -> str:
    return "Deployment name" if provider == "azure" else "Model"


def on_provider_change(provider: str):
    """Re-point the key, model, and Azure-endpoint boxes at the chosen provider."""
    p = PROVIDERS.get(provider) or PROVIDERS["mock"]
    is_mock = provider == "mock"
    return (
        gr.update(
            visible=not is_mock,
            label=p["key_label"] or "API key",
            placeholder=p.get("placeholder", ""),
            value="",
        ),
        gr.update(
            visible=not is_mock,
            label=_model_label(provider),
            choices=p["models"],
            value=None,
        ),
        gr.update(visible=provider == "azure"),
    )


def apply_provider(provider: str, key: str, model: str, azure_endpoint: str):
    """Pin the AI provider (and optionally its model) — no restart needed.

    A blank key or model means "keep whatever .env already supplied", so an
    operator can switch providers without re-pasting values already configured.
    Returns the refreshed banner and a blanked key box so the secret does not
    linger in the DOM.
    """
    provider = (provider or "mock").strip().lower()
    if provider not in PROVIDERS:
        raise gr.Error(f"Unknown provider {provider!r}.")
    spec = PROVIDERS[provider]

    os.environ["AI_PROVIDER"] = provider
    _UI_INJECTED.add("AI_PROVIDER")
    if provider != "mock":
        _set_env(spec["key_env"], (key or "").strip())
        # One picked model drives every purpose for this provider.
        for env_name in spec["model_envs"]:
            _set_env(env_name, (model or "").strip())
    if provider == "azure":
        _set_env("AZURE_CHAT_OPENAI_ENDPOINT", (azure_endpoint or "").strip())
    get_settings.cache_clear()

    mode = ai_mode()
    if mode != provider:
        # active_ai_provider falls back to mock when the pinned provider is
        # missing credentials. Say exactly what's missing instead of letting the
        # operator discover it only from the banner after a full run.
        need = "an API key"
        if provider == "azure":
            need = "an API key AND an endpoint"
        raise gr.Error(
            f"Selected '{provider}' but it fell back to '{mode}' — it needs {need}. "
            f"Paste it above, or set it in .env and click Reload."
        )
    gr.Info(f"AI provider is now: {mode} ({get_settings().model_for('classify')})")
    # Close the modal on success only. A raised gr.Error above aborts the whole
    # output update, so a failed apply leaves the modal open with the fields
    # intact for the operator to correct.
    return _mode_pill(), _mode_detail(), "", MODAL_CLOSED


def reload_env():
    """Re-read the .env file from disk, discarding anything typed into the UI.

    This is the path for an operator who edited .env while the server is up.
    UI-typed overrides are dropped first, otherwise they would shadow the file
    values and the reload would look like it silently did nothing.
    """
    _forget_ui_keys()
    get_settings.cache_clear()
    mode = ai_mode()
    gr.Info(f"Reloaded .env — AI provider is now: {mode}")
    # Modal stays open so the operator can see the reloaded state take effect
    # and keep adjusting; the radio is re-synced to whatever the file resolved to.
    return _mode_pill(), _mode_detail(), "", gr.update(value=mode)


# --------------------------------------------------------------------------- #
# UI                                                                          #
# --------------------------------------------------------------------------- #
def build_ui() -> gr.Blocks:
    # theme/css are set on Blocks (not launch) so `gradio ui.py` hot-reload —
    # which serves the module-level `demo` and calls launch() itself — still
    # applies them. This emits a Gradio 6 deprecation warning; that's expected.
    with gr.Blocks(title="AP Exception Handling Agent", theme=gr.themes.Soft(), css=CSS) as demo:
        _start_mode = ai_mode()

        with gr.Row(elem_classes=["app-header"]):
            with gr.Column(scale=6, min_width=300):
                gr.HTML(BRAND_HTML)
            with gr.Column(scale=1, min_width=150):
                mode_out = gr.HTML(_mode_pill())
            with gr.Column(scale=1, min_width=160):
                adv_btn = gr.Button("⚙️  Advanced Settings")

        gr.Markdown(
            "Ingest a queue of AP invoice exceptions → **classify** (AI) → **route** "
            "(deterministic rules) → **draft** vendor/internal communications → "
            "**prioritize**. Everything below is agent output for human review — nothing is sent."
        )

        # Settings "modal": a normally-hidden Column that CSS promotes to a
        # fixed, centered overlay. Gradio has no native dialog, and this keeps
        # the controls as real Gradio components (so they stay wired to Python)
        # rather than hand-rolled HTML.
        _start_provider = _start_mode if _start_mode in PROVIDERS else "mock"
        with gr.Column(elem_classes=["modal-wrap", "modal-closed"]) as settings_modal:
            with gr.Column(elem_classes=["modal-card"]):
                gr.Markdown("### ⚙️  Advanced settings — AI provider")
                gr.Markdown(
                    "Runs fully offline in **Mock** mode with no key at all. Pick a "
                    "provider and paste its key to switch — applies immediately, "
                    "**no restart**.\n\n"
                    "Keys live in this *server process* only (never written to `.env`), "
                    "so they are shared by every browser tab and lost on restart. Use "
                    "`.env` for anything persistent, then **Reload from .env** — that "
                    "discards anything typed here, so the file wins."
                )
                modal_status = gr.HTML(_mode_detail())
                provider_in = gr.Dropdown(
                    choices=PROVIDER_CHOICES,
                    value=_start_provider,
                    label="Provider",
                    filterable=False,
                )
                key_in = gr.Textbox(
                    label="API key", type="password",
                    placeholder="sk-ant-...",
                    visible=_start_provider != "mock",
                )
                model_in = gr.Dropdown(
                    label=_model_label(_start_provider),
                    choices=PROVIDERS[_start_provider]["models"],
                    value=None,
                    # Free-text so a model released after this build — or an Azure
                    # deployment with any name — can still be entered.
                    allow_custom_value=True,
                    visible=_start_provider != "mock",
                    info="Leave blank to keep the model already set in .env.",
                )
                azure_endpoint_in = gr.Textbox(
                    label="AZURE_CHAT_OPENAI_ENDPOINT",
                    placeholder="https://<resource>.openai.azure.com/",
                    visible=_start_provider == "azure",
                )
                with gr.Row():
                    key_btn = gr.Button("Apply provider", variant="primary", scale=2)
                    reload_btn = gr.Button("Reload .env", scale=1)
                    close_btn = gr.Button("Close", scale=1)

        with gr.Row():
            with gr.Column(scale=2):
                file_in = gr.File(label="Exception queue (CSV)", file_types=[".csv"])
            with gr.Column(scale=1, min_width=180):
                run_btn = gr.Button("▶  Run agent", variant="primary", size="lg")
                sample_btn = gr.Button("Load sample")

        status_out = gr.HTML()

        with gr.Tabs():
            with gr.Tab("Overview"):
                kpi_out = gr.HTML()
                gr.Markdown("### Breakdowns")
                breakdown_out = gr.HTML()
            with gr.Tab("Exceptions"):
                table_out = gr.Dataframe(
                    headers=TABLE_HEADERS, label="Per-invoice results", wrap=True,
                    interactive=False,
                )
            with gr.Tab("Communications"):
                drafts_out = gr.HTML(elem_classes=["drafts-panel", "dark-scroll"])
            with gr.Tab("Rejected rows"):
                gr.Markdown(
                    "Rows that failed ingestion validation are quarantined here — "
                    "the rest of the queue still runs."
                )
                quarantined_out = gr.Dataframe(
                    headers=["Row #", "Invoice", "Reason code", "Reason"],
                    wrap=True, interactive=False,
                )
            with gr.Tab("Report JSON"):
                download_out = gr.File(label="Download full report (.json)")
                raw_out = gr.Code(
                    label="Full JSON report", language="json",
                    max_lines=22, elem_classes=["json-report", "dark-scroll"],
                )

        outputs = [
            status_out, kpi_out, breakdown_out, table_out,
            drafts_out, quarantined_out, raw_out, download_out,
        ]
        run_btn.click(process, inputs=file_in, outputs=outputs)
        sample_btn.click(load_sample, outputs=file_in)
        adv_btn.click(lambda: MODAL_OPEN, outputs=settings_modal)
        close_btn.click(lambda: MODAL_CLOSED, outputs=settings_modal)
        provider_in.change(
            on_provider_change,
            inputs=provider_in,
            outputs=[key_in, model_in, azure_endpoint_in],
        )
        key_btn.click(
            apply_provider,
            inputs=[provider_in, key_in, model_in, azure_endpoint_in],
            outputs=[mode_out, modal_status, key_in, settings_modal],
        )
        reload_btn.click(
            reload_env, outputs=[mode_out, modal_status, key_in, provider_in]
        )

    return demo


# Module-level Blocks instance. `gradio ui.py` (hot reload) discovers and serves
# this; `python ui.py` launches it directly below.
demo = build_ui()


if __name__ == "__main__":
    demo.launch(inbrowser=True)
