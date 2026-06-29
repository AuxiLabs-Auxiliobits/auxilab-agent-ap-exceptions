"""Resolution path schemas."""
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ResolutionPath(str, Enum):
    AUTO_APPROVE = "AUTO_APPROVE"
    REQUEST_PO = "REQUEST_PO"
    ESCALATE_CONTROLLER = "ESCALATE_CONTROLLER"
    HOLD_INVESTIGATION = "HOLD_INVESTIGATION"
    VENDOR_VALIDATION_REVIEW = "VENDOR_VALIDATION_REVIEW"
    REQUEST_GRN = "REQUEST_GRN"
    MANUAL_REVIEW = "MANUAL_REVIEW"


# Human-readable "recommended approach" labels — the operator-facing wording (SLA
# digest email + spreadsheet, Slack card, assistant). The labels live in
# ``resolution_labels.json`` (this directory): the SINGLE source of truth shared
# with the frontend, which generates ``Frontend/src/lib/resolutionLabels.ts`` from
# the same file via ``Backend/scripts/gen_resolution_labels.py``. Edit the JSON,
# then run that script (a pytest fails if the generated TS is stale).
_LABELS_PATH = Path(__file__).with_name("resolution_labels.json")
RESOLUTION_PATH_LABELS: dict[str, str] = json.loads(
    _LABELS_PATH.read_text(encoding="utf-8")
)

# Fail fast on drift: the JSON must label exactly the enum's members.
_enum_values = {p.value for p in ResolutionPath}
if RESOLUTION_PATH_LABELS.keys() != _enum_values:
    raise RuntimeError(
        "resolution_labels.json out of sync with ResolutionPath: "
        f"missing={sorted(_enum_values - RESOLUTION_PATH_LABELS.keys())} "
        f"extra={sorted(RESOLUTION_PATH_LABELS.keys() - _enum_values)}"
    )


def resolution_path_label(path: object) -> str:
    """Friendly "recommended approach" label for a resolution path
    (``ESCALATE_CONTROLLER`` → ``"Escalate to Controller"``).

    Accepts a :class:`ResolutionPath`, its raw string value, or ``None``. An
    unknown/new code is humanized (``"SOME_NEW_PATH"`` → ``"Some New Path"``) so
    it never renders blank; ``None``/empty returns ``""``."""
    if path is None:
        return ""
    key = path.value if isinstance(path, ResolutionPath) else str(path)
    if not key:
        return ""
    return RESOLUTION_PATH_LABELS.get(key) or key.replace("_", " ").title()


class ResolutionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    resolution_path: ResolutionPath
    rule_id: str
    rule_version: str
    rule_trace: list[str]
    requires_communication: bool
    sla_hours: int
