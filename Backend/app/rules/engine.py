"""Deterministic rules engine for AP resolution routing.

This module is intentionally pure: no AI calls, no external IO at evaluation
time, no randomness. Given the same row + classification + policy version,
output is identical and the rule trace is reproducible — a hard requirement
for SOX auditability.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from app.schemas import (
    ClassificationResult,
    ExceptionRow,
    ResolutionDecision,
    ResolutionPath,
)

# Cheap parser for "Invoice exceeds PO by 8%" / "12.5% variance" / etc.
# Falls back to None when no pct is present; rules that need it then fail
# to match (predictable behavior).
_VARIANCE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_variance_pct(description: str) -> float | None:
    m = _VARIANCE_RE.search(description or "")
    return float(m.group(1)) if m else None


class RulePredicate(BaseModel):
    model_config = ConfigDict(extra="allow")


class RuleAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolution_path: ResolutionPath
    requires_communication: bool
    sla_hours: int


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    description: str = ""
    when: dict[str, Any]
    then: RuleAction


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    rules: list[Rule]


def validate_policy(raw: Any) -> Policy:
    """Validate a raw policy document into a Policy, enforcing the catch-all rule.

    Used both for the on-disk default and for tenant-supplied custom policies, so
    a per-org rulebook can never be saved without a final catch-all (empty
    ``when:``) — the safety invariant that guarantees every invoice is routed."""
    policy = Policy.model_validate(raw)
    if not policy.rules or policy.rules[-1].when != {}:
        raise ValueError(
            "Policy is missing a catch-all rule (empty `when:`) as its final entry. "
            "Refusing to load — this is an unsafe configuration."
        )
    return policy


def load_policy(path: str | Path) -> Policy:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return validate_policy(raw)


def _match_predicate(
    predicate: dict[str, Any],
    row: ExceptionRow,
    classification: ClassificationResult,
) -> tuple[bool, list[str]]:
    """Evaluate a single rule's `when` block. Returns (matched, per-key trace)."""
    trace: list[str] = []
    amount = float(row.invoice_amount)
    days = row.days_outstanding
    variance = parse_variance_pct(row.exception_description)
    exc_type = classification.primary_exception_type.value
    confidence = classification.confidence_score

    for key, expected in predicate.items():
        ok = False
        detail = ""
        if key == "exception_type":
            ok = exc_type == expected
            detail = f"exception_type={exc_type!r} ?== {expected!r}"
        elif key == "amount_lt":
            ok = amount < float(expected)
            detail = f"amount={amount} < {expected}"
        elif key == "amount_lte":
            ok = amount <= float(expected)
            detail = f"amount={amount} <= {expected}"
        elif key == "amount_gte":
            ok = amount >= float(expected)
            detail = f"amount={amount} >= {expected}"
        elif key == "amount_gt":
            ok = amount > float(expected)
            detail = f"amount={amount} > {expected}"
        elif key == "days_outstanding_gte":
            ok = days >= int(expected)
            detail = f"days={days} >= {expected}"
        elif key == "days_outstanding_gt":
            ok = days > int(expected)
            detail = f"days={days} > {expected}"
        elif key == "variance_pct_lt":
            ok = variance is not None and variance < float(expected)
            detail = f"variance_pct={variance} < {expected}"
        elif key == "variance_pct_gte":
            ok = variance is not None and variance >= float(expected)
            detail = f"variance_pct={variance} >= {expected}"
        elif key == "severity_in":
            sev = classification.severity.value
            ok = sev in expected
            detail = f"severity={sev} in {expected}"
        elif key == "confidence_lt":
            ok = confidence < float(expected)
            detail = f"confidence={confidence} < {expected}"
        else:
            raise ValueError(f"Unknown rule predicate key: {key!r}")
        trace.append(f"{'PASS' if ok else 'FAIL'} {detail}")
        if not ok:
            return False, trace
    return True, trace


class RulesEngine:
    """First-match-wins rule evaluator."""

    def __init__(self, policy: Policy):
        self.policy = policy

    @classmethod
    def from_path(cls, path: str | Path) -> RulesEngine:
        return cls(load_policy(path))

    def evaluate(
        self,
        row: ExceptionRow,
        classification: ClassificationResult,
        *,
        auto_approve_ceiling: Decimal | None = None,
    ) -> ResolutionDecision:
        """Resolve ``row`` to a decision (first-match-wins).

        ``auto_approve_ceiling``: a materiality backstop. When set, an invoice at
        or above this amount can never auto-approve even if a rule says so — it's
        overridden to MANUAL_REVIEW and the override is recorded in the trace.
        This guards against a mis-calibrated or too-lenient AUTO_APPROVE rule
        independently of how the policy is authored.
        """
        full_trace: list[str] = []
        for rule in self.policy.rules:
            matched, trace = _match_predicate(rule.when, row, classification)
            full_trace.append(f"-- rule {rule.id} --")
            full_trace.extend(trace)
            if matched:
                full_trace.append(f"MATCHED {rule.id}")
                path = rule.then.resolution_path
                requires_comms = rule.then.requires_communication
                sla = rule.then.sla_hours
                rule_id = rule.id
                if (
                    path == ResolutionPath.AUTO_APPROVE
                    and auto_approve_ceiling is not None
                    and auto_approve_ceiling > 0
                    and row.invoice_amount >= auto_approve_ceiling
                ):
                    full_trace.append(
                        f"CEILING amount={float(row.invoice_amount)} "
                        f">= {float(auto_approve_ceiling)} → override AUTO_APPROVE "
                        f"to MANUAL_REVIEW (materiality guardrail)"
                    )
                    path = ResolutionPath.MANUAL_REVIEW
                    requires_comms = False
                    rule_id = f"{rule.id}+materiality_ceiling"
                return ResolutionDecision(
                    invoice_id=row.invoice_id,
                    resolution_path=path,
                    rule_id=rule_id,
                    rule_version=self.policy.version,
                    rule_trace=full_trace,
                    requires_communication=requires_comms,
                    sla_hours=sla,
                )
        # Unreachable if load_policy enforced catch-all.
        raise RuntimeError("Rules engine fell through without matching catch-all")


# Convenience for callers that don't want to touch Decimal arithmetic.
def to_decimal(x: float | int | str) -> Decimal:
    return Decimal(str(x))
