"""Communication preview endpoints (read-only, no sending).

Render exactly what an outbound message will look like — the email HTML/text and
the Slack Block Kit payload — without dispatching anything. Two modes:

  POST /v1/preview/comms
      Render arbitrary content + optional signature/tone overrides. Powers the
      admin "branding" playground: tweak the signature/disclaimer and see the
      result live. Overrides are preview-only — they are NOT persisted (per-org
      saved settings come in a later phase).

  GET  /v1/runs/{run_id}/drafts/{invoice_id}/preview
      Render a real generated draft (tenant-scoped) so a reviewer can preview the
      exact message before sending it.

Both are read-only and never touch a provider or expose a secret.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_owned_run
from app.comms.email_template import render_html, render_text
from app.comms.providers.slack_webhook import _build_blocks, _to_mrkdwn
from app.config import Settings, get_settings
from app.schemas import CommChannel, CommunicationDraft

router = APIRouter(prefix="/v1", tags=["preview"])

_EMAIL_CHANNELS = {
    CommChannel.VENDOR_EMAIL,
    CommChannel.INTERNAL_EMAIL,
    CommChannel.FINANCE_NOTE,
}

_SAMPLE_BODY = (
    "Dear Vendor,\n\n"
    "We are reviewing invoice INV-2001 and found a price variance against the "
    "purchase order.\n\n"
    "- Invoiced unit price exceeds the PO by 14% on 3 line items\n"
    "- Quantity and totals otherwise match the goods receipt\n\n"
    "Could you confirm the correct pricing or issue a corrected invoice?\n\n"
    "Thank you,"
)


class PreviewRequest(BaseModel):
    """Content + optional preview-only branding overrides."""

    channel: CommChannel = CommChannel.VENDOR_EMAIL
    invoice_id: str = "INV-2001"
    subject: str | None = "Action required: invoice INV-2001 — price variance"
    body: str = Field(default=_SAMPLE_BODY, min_length=1, max_length=4000)
    tone: str = "professional"

    # Optional context for the Slack field grid.
    vendor_name: str | None = "Workday"
    invoice_amount: float | None = 27500
    severity: str | None = "HIGH"
    exception_type: str | None = "Price Variance"
    resolution_path: str | None = "ESCALATE_CONTROLLER"
    sla_hours: int | None = 8
    days_outstanding: int | None = 12

    # Optional signature / footer / brand overrides (preview-only — not persisted).
    signature_name: str | None = None
    signature_team: str | None = None
    signature_company: str | None = None
    signature_disclaimer: str | None = None
    disclose_ai_assistance: bool | None = None
    brand_color: str | None = None
    logo_url: str | None = None


def _apply_overrides(settings: Settings, req: PreviewRequest) -> Settings:
    """A copy of settings with any provided signature/footer overrides applied.

    Never mutates the cached global settings — overrides live only for this
    render so the playground can experiment without side effects."""
    updates: dict = {}
    if req.signature_name is not None:
        updates["comms_signature_name"] = req.signature_name
    if req.signature_team is not None:
        updates["comms_signature_team"] = req.signature_team
    if req.signature_company is not None:
        updates["comms_signature_company"] = req.signature_company
    if req.signature_disclaimer is not None:
        updates["comms_signature_disclaimer"] = req.signature_disclaimer
    if req.disclose_ai_assistance is not None:
        updates["comms_disclose_ai_assistance"] = req.disclose_ai_assistance
    if req.brand_color is not None:
        updates["comms_brand_color"] = req.brand_color
    if req.logo_url is not None:
        updates["comms_logo_url"] = req.logo_url
    return settings.model_copy(update=updates) if updates else settings


def _render(draft: CommunicationDraft, settings: Settings, context: dict) -> dict:
    """Render both representations so the UI can show either medium."""
    return {
        "channel": draft.channel.value,
        "subject": draft.subject,
        "email": {
            "html": render_html(draft, settings),
            "text": render_text(draft, settings),
        },
        "slack": {
            "blocks": _build_blocks(draft, context),
            "text": _to_mrkdwn(draft.body),
        },
    }


@router.post("/preview/comms")
def preview_comms(req: PreviewRequest = Body(default=None)) -> dict:
    """Render arbitrary content (+ optional branding overrides). Preview only."""
    req = req or PreviewRequest()
    settings = _apply_overrides(get_settings(), req)
    draft = CommunicationDraft(
        invoice_id=req.invoice_id,
        channel=req.channel,
        recipient_hint="preview",
        subject=req.subject,
        body=req.body,
        tone=req.tone,
        template_id="preview",
        model_id="preview",
    )
    context = {
        "vendor_name": req.vendor_name,
        "invoice_amount": req.invoice_amount,
        "severity": req.severity,
        "exception_type": req.exception_type,
        "resolution_path": req.resolution_path,
        "sla_hours": req.sla_hours,
        "days_outstanding": req.days_outstanding,
    }
    return _render(draft, settings, context)


def _draft_context(state: dict, invoice_id: str) -> dict:
    """Slack field context pulled from real run state (vendor, amount, severity…)."""
    ctx: dict = {}
    row = next((r for r in state.get("rows", []) if r.invoice_id == invoice_id), None)
    c = next((c for c in state.get("classifications", []) if c.invoice_id == invoice_id), None)
    res = next((x for x in state.get("resolutions", []) if x.invoice_id == invoice_id), None)
    if row is not None:
        ctx["vendor_name"] = row.vendor_name
        ctx["invoice_amount"] = float(row.invoice_amount)
        ctx["days_outstanding"] = row.days_outstanding
    if c is not None:
        ctx["severity"] = c.severity.value
        ctx["exception_type"] = c.primary_exception_type.value
    if res is not None:
        # Raw routing code — the Slack renderer maps it to the friendly
        # "Recommended approach" label (single source of truth).
        ctx["resolution_path"] = res.resolution_path.value
        ctx["sla_hours"] = res.sla_hours
    return ctx


@router.get("/runs/{run_id}/drafts/{invoice_id}/preview")
def preview_draft(
    run_id: str,
    invoice_id: str,
    state: dict = Depends(get_owned_run),
) -> dict:
    """Render a real generated draft as it would be sent. Read-only."""
    draft = next(
        (d for d in state.get("drafts", []) if d.invoice_id == invoice_id),
        None,
    )
    if draft is None:
        raise HTTPException(404, f"no draft for invoice {invoice_id}")
    return _render(draft, get_settings(), _draft_context(state, invoice_id))
