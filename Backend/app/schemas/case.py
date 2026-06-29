"""Case — the human resolution lifecycle for a single exception.

The pipeline classifies, routes, and drafts; a *case* tracks what a human did
afterwards, so an exception can be followed all the way to closure rather than
ending at "drafted/sent".
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class CaseStatus(str, Enum):
    OPEN = "OPEN"                # untouched — needs action
    IN_PROGRESS = "IN_PROGRESS"  # actioned, awaiting an outcome (e.g. vendor reply)
    RESOLVED = "RESOLVED"        # closed successfully (PO received, credit issued, approved)
    WONT_FIX = "WONT_FIX"        # closed without pursuing (accepted / written off)


# Terminal states no longer count against follow-up.
CLOSED_STATUSES = frozenset({CaseStatus.RESOLVED, CaseStatus.WONT_FIX})


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_id: str
    status: CaseStatus = CaseStatus.OPEN
    note: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None
