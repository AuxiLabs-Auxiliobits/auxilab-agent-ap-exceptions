"""
Queue Formatter

Assembles the final prioritised exception work queue and summary dashboard
based on the aggregated InvoiceResult objects.

v3.0 additions:
  - valid_invoice_queue.csv and exception_invoice_queue.csv output files
  - Business value metrics: blocked_payment_value, potential_duplicate_payment_value, auto_resolved_value
  - Dashboard: valid_invoice_value, auto_resolved_count, auto_resolved_value
"""

import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from invoice_processing.core.resolution_router import InvoiceResult

logger = logging.getLogger("APException.Formatter")

# Output directory
_OUTPUT_DIR = (
    Path(__file__).resolve().parent.parent / "data" / "exception_output"
)

_DUPLICATE_TYPES = {"Exact Duplicate Invoice", "Potential Duplicate Invoice"}


class QueueFormatter:
    """
    Assembles the final prioritised output from all pipeline stages.
    """

    def build(
        self,
        invoices: list[InvoiceResult],
        communications: dict[str, str] = None,
    ) -> dict:
        """
        Build the full priority queue output.

        Args:
            invoices: list of InvoiceResult objects
            communications: dict mapping invoice_id to drafted communication text

        Returns:
            dict with priority_queue, dashboard, output_path.
        """
        if communications is None:
            communications = {}

        exception_records = []
        auto_resolved_records = []
        valid_invoices = []

        for inv in invoices:
            record = inv.to_dict()
            record["communication_draft"] = communications.get(inv.invoice_id, "")
            
            excs = record.get("final_exception_list", [])
            is_valid = len(excs) == 0 or (len(excs) == 1 and excs[0].get("primary_type") == "VALID")
            
            if is_valid:
                valid_invoices.append({
                    "invoice_id": record["invoice_id"],
                    "invoice_amount": record["invoice_amount"],
                    "decision_trace": record["decision_trace"],
                })
            elif record.get("auto_resolved"):
                auto_resolved_records.append(record)
            else:
                exception_records.append(record)

        # Sort descending by normalized_priority_score
        priority_queue = sorted(exception_records, key=lambda r: r.get("normalized_priority_score", 0.0), reverse=True)
        auto_resolved_queue = sorted(auto_resolved_records, key=lambda r: r.get("raw_priority_score", 0.0), reverse=True)

        dashboard = self._build_dashboard(exception_records, auto_resolved_records, valid_invoices)
        output_path = self._write_outputs(priority_queue, auto_resolved_queue, dashboard, valid_invoices)

        return {
            "priority_queue": priority_queue,
            "dashboard": dashboard,
            "total_invoices_in_exception": len(exception_records) + len(auto_resolved_records) + len(valid_invoices),
            "output_path": str(output_path),
        }

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def _build_dashboard(
        self, exception_records: list[dict], auto_resolved_records: list[dict], valid_invoices: list[dict]
    ) -> dict:
        """Build the summary dashboard stats including business value KPIs."""
        total_invoices = len(exception_records) + len(auto_resolved_records) + len(valid_invoices)
        escalations = 0
        payments_blocked = 0
        total_value_blocked = 0.0
        multi_exception_count = 0
        sum_raw_priority_score = 0.0
        sum_normalized_priority_score = 0.0
        auto_resolved_count = 0
        auto_resolved_value = 0.0

        dup_groups = {}
        blocked_dup_groups = {}
        by_type: dict[str, int] = {}

        for r in exception_records + auto_resolved_records:
            amount = float(r.get("invoice_amount", 0))
            excs = r.get("final_exception_list", [])
            sum_raw_priority_score += float(r.get("raw_priority_score", 0))
            sum_normalized_priority_score += float(r.get("normalized_priority_score", 0))

            if r.get("escalation_required"):
                escalations += 1

            # Track potential duplicate value (group by vendor, invoice_number)
            has_duplicate = any(
                e.get("primary_type") in _DUPLICATE_TYPES for e in excs
            )

            if r.get("payment_blocked"):
                payments_blocked += 1
                if has_duplicate:
                    key = (r.get("vendor_name"), r.get("invoice_number"))
                    if key not in blocked_dup_groups:
                        blocked_dup_groups[key] = []
                    blocked_dup_groups[key].append(amount)
                else:
                    total_value_blocked += amount

            if r.get("auto_resolved"):
                auto_resolved_count += 1
                auto_resolved_value += amount

            if len(excs) > 1:
                multi_exception_count += 1

            if has_duplicate:
                key = (r.get("vendor_name"), r.get("invoice_number"))
                if key not in dup_groups:
                    dup_groups[key] = []
                dup_groups[key].append(amount)

            for e in excs:
                t = e.get("primary_type", "Other")
                by_type[t] = by_type.get(t, 0) + 1

        potential_dup_value = 0.0
        for key, amounts in dup_groups.items():
            if amounts:
                potential_dup_value += amounts[0]

        for key, amounts in blocked_dup_groups.items():
            if amounts:
                total_value_blocked += amounts[0]

        avg_raw_priority = (sum_raw_priority_score / total_invoices) if total_invoices > 0 else 0.0
        avg_norm_priority = (sum_normalized_priority_score / total_invoices) if total_invoices > 0 else 0.0

        total_exception_count = sum(by_type.values())
        other_count = by_type.get("Other", 0)
        percentage_other = (
            round((other_count / total_exception_count * 100), 1)
            if total_exception_count > 0 else 0.0
        )

        # Valid invoice metrics
        valid_invoice_value = round(
            sum(float(v.get("invoice_amount", 0)) for v in valid_invoices), 2
        )

        return {
            # Volume metrics
            "total_invoices": total_invoices,
            "valid_invoices_count": len(valid_invoices),
            "escalations_required": escalations,
            "auto_resolved_count": auto_resolved_count,
            "payments_blocked": payments_blocked,
            "multi_exception_invoice_count": multi_exception_count,
            "average_normalized_priority_score": round(avg_norm_priority, 2),
            "exception_count_by_type": dict(
                sorted(by_type.items(), key=lambda x: -x[1])
            ),
            "percentage_other": percentage_other,
            "communication_drafts_produced": sum(
                1 for r in exception_records + auto_resolved_records if r.get("communication_draft")
            ),
            # Business value KPIs
            "business_value_metrics": {
                "valid_invoice_value": valid_invoice_value,
                "blocked_payment_value": round(total_value_blocked, 2),
                "potential_duplicate_payment_value": round(potential_dup_value, 2),
                "auto_resolved_value": round(auto_resolved_value, 2),
            },
        }

    # ------------------------------------------------------------------
    # Output writers
    # ------------------------------------------------------------------

    def _write_outputs(
        self,
        priority_queue: list[dict],
        auto_resolved_queue: list[dict],
        dashboard: dict,
        valid_invoices: list[dict],
    ) -> Path:
        """Write all output files and return the run directory path."""
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        run_dir = _OUTPUT_DIR / ts
        run_dir.mkdir(parents=True, exist_ok=True)

        # JSON outputs
        with open(run_dir / "priority_queue.json", "w") as f:
            json.dump(priority_queue, f, indent=2, default=str)

        with open(run_dir / "dashboard.json", "w") as f:
            json.dump(dashboard, f, indent=2, default=str)

        # Communications
        comms_dir = run_dir / "communications"
        comms_dir.mkdir(exist_ok=True)
        for record in priority_queue:
            draft = record.get("communication_draft", "")
            if draft:
                safe_id = str(record["invoice_id"]).replace("/", "-")
                with open(comms_dir / f"{safe_id}_draft.txt", "w") as f:
                    f.write(draft)

        # exception_invoice_queue.csv
        self._write_exception_csv(run_dir / "exception_invoice_queue.csv", priority_queue)

        # auto_resolved_queue.csv
        self._write_exception_csv(run_dir / "auto_resolved_queue.csv", auto_resolved_queue)

        # valid_invoice_queue.csv
        self._write_valid_csv(run_dir / "valid_invoice_queue.csv", valid_invoices)

        logger.info(f"Wrote all outputs to {run_dir}")
        return run_dir

    def _write_exception_csv(self, path: Path, priority_queue: list[dict]) -> None:
        """Write exception_invoice_queue.csv."""
        fieldnames = [
            "invoice_id",
            "invoice_amount",
            "priority_tier",
            "payment_blocked",
            "escalation_required",
            "escalation_decision_reason",
            "normalized_priority_score",
            "raw_priority_score",
            "sla_hours",
            "auto_resolved",
            "auto_close_flag",
            "communication_required",
            "communication_draft",
            "root_cause_categories",
            "resolution_owners",
            "exceptions_summary",
            "skipped_exceptions_trace",
            "decision_trace"
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in priority_queue:
                writer.writerow({
                    "invoice_id": r.get("invoice_id"),
                    "invoice_amount": r.get("invoice_amount"),
                    "priority_tier": r.get("priority_tier", "LOW"),
                    "payment_blocked": r.get("payment_blocked"),
                    "escalation_required": r.get("escalation_required"),
                    "escalation_decision_reason": r.get("escalation_decision_reason", ""),
                    "normalized_priority_score": r.get("normalized_priority_score"),
                    "raw_priority_score": r.get("raw_priority_score"),
                    "sla_hours": r.get("sla_hours"),
                    "auto_resolved": r.get("auto_resolved", False),
                    "auto_close_flag": r.get("auto_close_flag", False),
                    "communication_required": r.get("communication_required"),
                    "communication_draft": r.get("communication_draft", ""),
                    "root_cause_categories": " | ".join(r.get("root_cause_categories", [])),
                    "resolution_owners": " | ".join(r.get("resolution_owners", [])),
                    "exceptions_summary": "; ".join(
                        f"{e.get('primary_type', 'Unknown')} ({e.get('confidence', 0):.2f})"
                        for e in r.get("final_exception_list", [])
                    ),
                    "skipped_exceptions_trace": json.dumps(r.get("skipped_exceptions_trace", [])),
                    "decision_trace": " | ".join(r.get("decision_trace", [])),
                })

    def _write_valid_csv(self, path: Path, valid_invoices: list[dict]) -> None:
        """Write valid_invoice_queue.csv."""
        fieldnames = ["invoice_id", "invoice_amount", "decision_trace"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for v in valid_invoices:
                trace = v.get("decision_trace", [])
                trace_str = " | ".join(trace) if isinstance(trace, list) else str(trace)
                writer.writerow({
                    "invoice_id": v.get("invoice_id"),
                    "invoice_amount": v.get("invoice_amount"),
                    "decision_trace": trace_str,
                })
