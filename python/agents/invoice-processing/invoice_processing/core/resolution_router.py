"""
Resolution Router

Purely deterministic — NO LLM.

Reads exception_resolution_rules.yaml and assigns a resolution path,
severity, confidence, priority score, and root cause to each classified exception,
and aggregates them into an InvoiceResult.

v3.0 additions:
  - Dependency-aware exception evaluation (rule_dependencies in YAML)
  - Rule priority / short-circuiting (stop_further_checks per rule)
  - Real invoice_age_days computed from invoice_date field
  - auto_resolved flag on InvoiceResult
  - Age Weight trace in decision_trace
"""

import logging
import os
from datetime import datetime, date
from pathlib import Path
from dataclasses import dataclass, field
import yaml

from invoice_processing.core.exception_classifier import ExceptionClassification

logger = logging.getLogger("APException.Router")

# ---------------------------------------------------------------------------
# Config path
# ---------------------------------------------------------------------------

_RULES_PATH = (
    Path(__file__).resolve().parent.parent
    / "shared_libraries"
    / "exception_resolution_rules.yaml"
)

# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class InvoiceResult:
    """Aggregated resolution result for a single invoice."""
    invoice_id: str
    invoice_amount: float
    invoice_age_days: int
    evaluated_exceptions: list[ExceptionClassification] = field(default_factory=list)
    final_exception_list: list[ExceptionClassification] = field(default_factory=list)
    priority_tier: str = "LOW"
    payment_blocked: bool = False
    escalation_required: bool = False
    normalized_priority_score: float = 0.0
    raw_priority_score: float = 0.0
    root_cause_categories: list[str] = field(default_factory=list)
    resolution_owners: list[str] = field(default_factory=list)
    sla_hours: int = 0
    decision_trace: list[str] = field(default_factory=list)
    auto_resolved: bool = False
    auto_close_flag: bool = False
    communication_required: bool = False
    escalation_decision_reason: str = ""
    skipped_exceptions_trace: list[dict] = field(default_factory=list)
    vendor_name: str = ""
    invoice_number: str = ""

    @property
    def exceptions(self) -> list[ExceptionClassification]:
        return self.evaluated_exceptions

    @property
    def priority_score(self) -> float:
        return self.normalized_priority_score

    def to_dict(self) -> dict:
        return {
            "invoice_id": self.invoice_id,
            "invoice_amount": self.invoice_amount,
            "invoice_age_days": self.invoice_age_days,
            "vendor_name": self.vendor_name,
            "invoice_number": self.invoice_number,
            "final_exception_list": [
                {
                    "primary_type": e.primary_type,
                    "root_cause_hypothesis": e.root_cause_hypothesis,
                    "recommended_action": e.recommended_action,
                    "evidence_used": e.evidence_used,
                    "evidence_checked": e.evidence_checked,
                    "missing_data": e.missing_data,
                    "business_rule_triggered": e.business_rule_triggered,
                    "confidence": getattr(e, "confidence", 0.0)
                }
                for e in self.final_exception_list
            ],
            "priority_tier": self.priority_tier,
            "payment_blocked": self.payment_blocked,
            "escalation_required": self.escalation_required,
            "escalation_decision_reason": self.escalation_decision_reason,
            "normalized_priority_score": self.normalized_priority_score,
            "raw_priority_score": self.raw_priority_score,
            "root_cause_categories": self.root_cause_categories,
            "resolution_owners": self.resolution_owners,
            "sla_hours": self.sla_hours,
            "decision_trace": self.decision_trace,
            "skipped_exceptions_trace": self.skipped_exceptions_trace,
            "auto_resolved": self.auto_resolved,
            "auto_close_flag": self.auto_close_flag,
            "communication_required": self.communication_required,
        }

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class ResolutionRouter:
    """
    Assigns resolution paths to classified AP exceptions and groups by invoice.

    All logic is driven by exception_resolution_rules.yaml.
    No LLM calls — pure Python deterministic rules.
    """

    def __init__(self):
        self._rules = self._load_rules()

    def _load_rules(self) -> dict:
        """Load resolution rules from YAML config."""
        if not _RULES_PATH.exists():
            logger.warning(
                f"Resolution rules not found at {_RULES_PATH}. "
                "Using hardcoded defaults."
            )
            return {}
        with open(_RULES_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f)

    # ------------------------------------------------------------------
    # Age helpers
    # ------------------------------------------------------------------

    def _parse_age_days(self, invoice_date_str: str) -> int:
        """Compute invoice age in days from invoice_date string (YYYY-MM-DD)."""
        if not invoice_date_str or str(invoice_date_str).strip() in ("", "UNKNOWN"):
            return 0
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"):
            try:
                inv_date = datetime.strptime(str(invoice_date_str).strip(), fmt).date()
                reference_date_str = os.getenv("REFERENCE_DATE", date.today().isoformat())
                ref_date = date.fromisoformat(reference_date_str)
                age = (ref_date - inv_date).days
                return max(0, age)
            except ValueError:
                continue
        return 0

    def _age_score(self, days: int) -> int:
        """Return the age weight score for a given number of days outstanding."""
        weights = self._rules.get("priority_scoring_weights", {}).get("age", {})
        if days > 30:
            return int(weights.get("over_30_days", 30))
        elif days > 7:
            return int(weights.get("over_7_days", 15))
        else:
            return int(weights.get("recent", 5))

    # ------------------------------------------------------------------
    # Confidence helper
    # ------------------------------------------------------------------

    def _determine_confidence(self, exc: ExceptionClassification) -> float:
        """Calculate confidence based on evidence quality and missing data."""
        if getattr(exc, "confidence", 0.0) > 0.0:
            return exc.confidence

        rules = self._rules.get("confidence_scoring_rules", {})

        if exc.primary_type == "Unknown" or len(exc.missing_data) > 0:
            return float(rules.get("unknown", 0.20))

        evidence = exc.evidence_used.lower()
        if exc.primary_type in ("Exact Duplicate Invoice", "Potential Duplicate Invoice") and "history" in evidence:
            return float(rules.get("exact_duplicate_invoice_match", 1.00))
        if exc.primary_type == "Vendor Mismatch" and "fuzzy" in evidence:
            return float(rules.get("fuzzy_vendor_match", 0.75))
        if exc.primary_type == "Currency Mismatch":
            return float(rules.get("exact_currency_mismatch", 1.00))

        return float(rules.get("exact_erp_match", 1.00))

    # ------------------------------------------------------------------
    # Dependency helper
    # ------------------------------------------------------------------

    def _is_field_present(self, raw_invoice: dict, field_name: str) -> bool:
        """Return True if the field has a non-blank, non-UNKNOWN value."""
        val = str(raw_invoice.get(field_name, "")).strip()
        return bool(val) and val.upper() != "UNKNOWN"

    def _check_dependency(
        self, exc_type: str, raw_invoice: dict
    ) -> tuple[bool, str]:
        """
        Check whether all prerequisite fields for an exception type are present.

        Returns:
            (True, "")                   — all fields present, evaluation can proceed
            (False, "<skip_reason>")     — a required field is missing
        """
        deps = self._rules.get("rule_dependencies", {})
        required = deps.get(exc_type, {}).get("required_fields", [])
        for f in required:
            if not self._is_field_present(raw_invoice, f):
                reason = (
                    f"Skipped {exc_type} evaluation because "
                    f"required field '{f}' is missing."
                )
                return False, reason
        return True, ""

    # ------------------------------------------------------------------
    # Priority scoring
    # ------------------------------------------------------------------

    def _calculate_priority_score(
        self, amount: float, days: int, highest_severity: str, exception_count: int
    ) -> float:
        """Compute numeric priority score based on configured weights."""
        weights = self._rules.get("priority_scoring_weights", {})

        sev_weights = weights.get("severity", {})
        sev_score = sev_weights.get(highest_severity, sev_weights.get("Medium", 50))

        amt_weights = weights.get("amount", {})
        if amount > 10000:
            amt_score = amt_weights.get("high_value", 50)
        elif amount > 2500:
            amt_score = amt_weights.get("medium_value", 25)
        else:
            amt_score = amt_weights.get("low_value", 10)

        age_score = self._age_score(days)

        exc_weights = weights.get("exception_count", {})
        add_exc_score = exc_weights.get("additional_exception", 20)
        count_score = max(0, exception_count - 1) * add_exc_score
        count_score = min(30, count_score)

        return float(sev_score + amt_score + age_score + count_score)

    # ------------------------------------------------------------------
    # Main batch assignment
    # ------------------------------------------------------------------

    def assign_batch(
        self, raw_exceptions: list[dict], classifications: list[ExceptionClassification]
    ) -> list[InvoiceResult]:
        """
        Takes raw exceptions and their parsed classifications and returns
        aggregated InvoiceResults.

        Logic per invoice:
          1. For each exception, check rule_dependencies — skip + trace if unmet.
          2. Apply resolution rules (severity, payment_block, escalation, SLA).
          3. If stop_further_checks=true, halt processing remaining exceptions.
          4. Compute priority score (includes real age from invoice_date).
          5. Mark auto_resolved if ALL processed exceptions are auto_resolvable.
        """
        # Build lookup: invoice_id → {amount, days, raw_invoice_dict}
        raw_by_invoice: dict[str, dict] = {}
        for r in raw_exceptions:
            iid = r.get("invoice_id", "UNKNOWN")
            if iid not in raw_by_invoice:
                try:
                    amount = float(
                        str(r.get("invoice_amount", 0))
                        .replace(",", "")
                        .replace("$", "")
                        .strip()
                        or 0
                    )
                except (ValueError, TypeError):
                    amount = 0.0

                invoice_date_str = str(r.get("invoice_date", "")).strip()
                days = self._parse_age_days(invoice_date_str)

                raw_by_invoice[iid] = {
                    "amount": amount,
                    "days": days,
                    "raw": r,
                    "vendor_name": r.get("vendor_name", ""),
                    "invoice_number": r.get("invoice_number", ""),
                }

        # Group classifications by invoice_id
        class_by_invoice: dict[str, list[ExceptionClassification]] = {}
        for c in classifications:
            if not c.success:
                continue
            iid = c.invoice_id
            class_by_invoice.setdefault(iid, []).append(c)

        results: list[InvoiceResult] = []
        exc_rules = self._rules.get("exception_rules", {})

        priority_order = [
            "Missing Required Data",
            "Exact Duplicate Invoice",
            "Potential Duplicate Invoice",
            "Vendor Mismatch",
            "Currency Mismatch",
            "Amount Exceeds Tolerance",
            "GRN Not Received",
            "Other",
            "Unknown"
        ]

        def get_priority_index(exc_type: str) -> int:
            try:
                return priority_order.index(exc_type)
            except ValueError:
                return len(priority_order)

        all_required_fields = set()
        for deps in self._rules.get("rule_dependencies", {}).values():
            all_required_fields.update(deps.get("required_fields", []))

        for iid, raw_inv in raw_by_invoice.items():
            exc_list = class_by_invoice.get(iid, [])
            amount = raw_inv.get("amount", 0.0)
            days = raw_inv.get("days", 0)
            raw_invoice_dict = raw_inv.get("raw", {})

            result = InvoiceResult(
                invoice_id=iid,
                invoice_amount=amount,
                invoice_age_days=days,
                vendor_name=raw_inv.get("vendor_name", ""),
                invoice_number=raw_inv.get("invoice_number", "")
            )

            highest_severity = "Low"
            severity_rank = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
            
            missing_fields = []
            for f in all_required_fields:
                if not self._is_field_present(raw_invoice_dict, f):
                    missing_fields.append(f)

            po_missing = "po_number" in missing_fields
            other_missing = [f for f in missing_fields if f != "po_number"]

            has_po_not_found = any(e.primary_type == "PO Not Found" for e in exc_list)
            if po_missing and not has_po_not_found:
                injected = ExceptionClassification(
                    invoice_id=iid,
                    primary_type="PO Not Found",
                    root_cause_hypothesis="Deterministic router detected missing or blank PO number.",
                    evidence_used="Field missing: po_number",
                    business_rule_triggered="Phase 1 Master Rules",
                    success=True
                )
                injected.confidence = 1.0
                injected.source = "deterministic_router"
                exc_list.append(injected)

            has_missing_data_exc = any(e.primary_type == "Missing Required Data" for e in exc_list)
            if other_missing and not has_missing_data_exc:
                injected = ExceptionClassification(
                    invoice_id=iid,
                    primary_type="Missing Required Data",
                    root_cause_hypothesis="Deterministic router detected missing required fields.",
                    evidence_used=f"Fields missing: {', '.join(other_missing)}",
                    business_rule_triggered="Phase 1 Master Rules",
                    success=True
                )
                injected.confidence = 1.0
                injected.source = "deterministic_router"
                exc_list.append(injected)

            valid_exc_list = []
            for exc in exc_list:
                can_eval, skip_reason = self._check_dependency(exc.primary_type, raw_invoice_dict)
                if not can_eval:
                    result.decision_trace.append(skip_reason)
                    if not any(e.primary_type == "Missing Required Data" for e in valid_exc_list):
                        injected = ExceptionClassification(
                            invoice_id=iid,
                            primary_type="Missing Required Data",
                            root_cause_hypothesis="Deterministic router fallback for missing data.",
                            evidence_used=f"Dependency check failed: {skip_reason}",
                            business_rule_triggered="Phase 1 Master Rules",
                            success=True
                        )
                        injected.confidence = 1.0
                        injected.source = "deterministic_router"
                        valid_exc_list.append(injected)
                    continue
                valid_exc_list.append(exc)

            valid_exc_list.sort(key=lambda x: (get_priority_index(x.primary_type), x.primary_type))

            # ── Phase 1: Pure Detection & Evaluation ──────────────────
            for exc in valid_exc_list:
                exc_rule = exc_rules.get(exc.primary_type, exc_rules.get("Other", {}))
                
                # Assign confidence
                confidence = self._determine_confidence(exc)
                exc.confidence = confidence
                
                result.evaluated_exceptions.append(exc)
                result.decision_trace.append(
                    f"Evaluated {exc.primary_type} with confidence {confidence:.2f}."
                )

                # Compute overall Severity
                sev = exc_rule.get("severity", "Low")
                sla = int(exc_rule.get("sla_hours", 48))

                # Special rule: High value missing data
                if exc.primary_type == "Missing Required Data" and amount > 10000:
                    sev = "Critical"
                    sla = 4
                    result.decision_trace.append(
                        "Critical Priority applied: Missing Required Data on High Value Invoice (>10k). SLA reduced to 4h."
                    )

                if severity_rank.get(sev, 1) > severity_rank.get(highest_severity, 1):
                    highest_severity = sev

                # Compute overall SLA
                if result.sla_hours == 0 or sla < result.sla_hours:
                    result.sla_hours = sla
            
            # Compute Priority Score from the FULL evaluated set
            result.raw_priority_score = self._calculate_priority_score(
                amount, days, highest_severity, len(result.evaluated_exceptions)
            )
            norm_score = (result.raw_priority_score / 210.0) * 100.0
            result.normalized_priority_score = round(min(100.0, norm_score), 2)
            result.decision_trace.append(
                f"Calculated Priority Score: {result.normalized_priority_score} "
                f"from {len(result.evaluated_exceptions)} evaluated exceptions."
            )

            # ── Phase 2: Routing Engine (Constraints & Actions) ─────────
            stop_further = False
            stop_further_source = ""
            all_auto_resolvable = True

            # Calculate blocked dependencies
            blocked_by = {}
            rule_dependencies = self._rules.get("rule_dependencies", {})
            active_types = {e.primary_type for e in valid_exc_list}
            for active_type in active_types:
                deps = rule_dependencies.get(active_type, {})
                for blocked in deps.get("blocks", []):
                    if blocked not in blocked_by:
                        blocked_by[blocked] = active_type

            routed_exceptions = []

            final_exc_dict = {}

            for exc in result.evaluated_exceptions:
                exc_rule = exc_rules.get(exc.primary_type, exc_rules.get("Other", {}))

                # ── Short-circuit gate ──
                if stop_further:
                    result.decision_trace.append(
                        f"Skipped routing for '{exc.primary_type}' — stop_further_checks "
                        f"active from ({stop_further_source})."
                    )
                    result.skipped_exceptions_trace.append({
                        "skipped_rule": exc.primary_type,
                        "reason": f"Routing blocked by stop_further_checks ({stop_further_source})",
                        "confidence_if_evaluated": exc.confidence
                    })
                    continue

                # ── Dependency gate ──
                if exc.primary_type in blocked_by:
                    blocking_parent = blocked_by[exc.primary_type]
                    result.decision_trace.append(
                        f"Skipped routing for {exc.primary_type} due to {blocking_parent} dependency lock."
                    )
                    result.skipped_exceptions_trace.append({
                        "skipped_rule": exc.primary_type,
                        "reason": f"Routing lock by {blocking_parent}",
                        "confidence_if_evaluated": exc.confidence
                    })
                    continue
                
                # ── Deduplication logic ──
                if exc.primary_type not in final_exc_dict:
                    final_exc_dict[exc.primary_type] = exc
                else:
                    if exc.confidence > final_exc_dict[exc.primary_type].confidence:
                        final_exc_dict[exc.primary_type] = exc

                # ── Apply Routing Constraints ──
                routed_exceptions.append(exc.primary_type)
                
                if exc_rule.get("block_payment", False):
                    result.payment_blocked = True
                    result.decision_trace.append(f"Payment blocked by {exc.primary_type}.")

                if exc_rule.get("escalation_required", False):
                    result.escalation_required = True
                    result.decision_trace.append(f"Escalation required by {exc.primary_type}.")

                rc = exc_rule.get("root_cause_category")
                if rc and rc not in result.root_cause_categories:
                    result.root_cause_categories.append(rc)

                owner = exc_rule.get("resolution_owner")
                if owner and owner not in result.resolution_owners:
                    result.resolution_owners.append(owner)

                if exc_rule.get("communication_required", False):
                    result.communication_required = True

                if not exc_rule.get("auto_resolvable", False):
                    all_auto_resolvable = False

                if exc_rule.get("stop_further_checks", False):
                    result.decision_trace.append(
                        f"{exc.primary_type} has stop_further_checks=true. Remaining validations skip routing."
                    )
                    stop_further = True
                    stop_further_source = exc.primary_type

            # ── Post-processing: Over-Escalation Check ──────────────────
            pass

            # ── Auto-resolved decision ──────────────────────────────────
            if len(routed_exceptions) > 0 and (all_auto_resolvable or result.auto_close_flag):
                result.auto_resolved = True
                result.payment_blocked = False
                result.escalation_required = False
                result.decision_trace.append(
                    "Invoice automatically resolved. Payment and escalation blocks removed. Scores retained."
                )

            age_pts = self._age_score(days)
            result.decision_trace.append(
                f"Age Weight Applied: {age_pts} points (invoice age = {days} days)."
            )

            result.final_exception_list = list(final_exc_dict.values())

            if result.normalized_priority_score >= 75.0:
                result.priority_tier = "HIGH"
            elif result.normalized_priority_score >= 40.0:
                result.priority_tier = "MEDIUM"
            else:
                result.priority_tier = "LOW"
            result.decision_trace.append(f"Assigned Priority Tier: {result.priority_tier}")

            results.append(result)

        return results
