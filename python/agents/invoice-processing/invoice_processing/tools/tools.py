"""
Function tools for the Invoice Processing unified agent.

Combines inference tools (case discovery, pipeline execution) and
learning tools (case review, rule management, session logging).
"""

import ast
import json
import re
import sys
from pathlib import Path

# Resolve paths: tools.py -> tools/ -> invoice_processing/ (package root with data/ inside)
AGENT_PKG_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = AGENT_PKG_DIR / "data"
EXEMPLARY_DIR = AGENT_PKG_DIR / "exemplary_data"

# Ensure invoice_processing package and shared_libraries are importable
AGENT_ROOT = AGENT_PKG_DIR.parent  # invoice_processing/ (outer)
sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(AGENT_PKG_DIR / "shared_libraries"))

from ..core.case_loader import CaseLoaderAgent  # noqa: E402
from ..core.communication_drafter import CommunicationDrafter  # noqa: E402
from ..core.config import RULES_BOOK_PATH  # noqa: E402
from ..core.exception_classifier import ExceptionClassifier  # noqa: E402
from ..core.impact_assessor import ImpactAssessorAgent  # noqa: E402
from ..core.prompts import (  # noqa: E402
    RULE_DISCOVERY_SYSTEM_PROMPT,
    RULE_DISCOVERY_TASK_TEMPLATE,
    RULE_REVISION_TASK_TEMPLATE,
    extract_relevant_rules_book_sections,
)
from ..core.queue_formatter import QueueFormatter  # noqa: E402
from ..core.resolution_router import ResolutionRouter  # noqa: E402
from ..core.rule_writer import RuleWriterAgent  # noqa: E402
from ..core.safe_rule_orchestrator import SafeRuleOrchestrator  # noqa: E402
from ..core.schema_mapper import SchemaMapper  # noqa: E402
from ..core.session_logger import SessionLogger  # noqa: E402

# ---------------------------------------------------------------------------
# Module-level instances (singletons)
# ---------------------------------------------------------------------------

_case_loader = CaseLoaderAgent()
_impact_assessor = ImpactAssessorAgent()
_rule_writer = RuleWriterAgent()
_session_logger = SessionLogger()
_orchestrator = SafeRuleOrchestrator()

# Exception queue singletons
_exception_classifier = ExceptionClassifier()
_resolution_router = ResolutionRouter()
_communication_drafter = CommunicationDrafter()
_queue_formatter = QueueFormatter()
_schema_mapper = SchemaMapper()


def _safe_json_loads(text) -> dict:
    """Parse JSON/dict input from LLM, handling all common formats."""
    # If already a dict/list (ADK may pass structured objects), return directly
    if isinstance(text, (dict, list)):
        return text
    if not isinstance(text, str):
        text = str(text)
    # Strip markdown code fences if present
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Remove first line (```json) and last line (```)
        lines = [
            line for line in lines[1:] if not line.strip().startswith("```")
        ]
        stripped = "\n".join(lines).strip()
    # Try direct JSON parse
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass
    # Fix unescaped backslashes (common LLM error)
    try:
        cleaned = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", stripped)
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass
    # Try Python literal (single quotes, True/False/None)
    try:
        result = ast.literal_eval(stripped)
        if isinstance(result, (dict, list)):
            return result
    except (ValueError, SyntaxError):
        pass
    # Replace single quotes with double quotes
    try:
        cleaned = stripped.replace("'", '"')
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass
    # Log what we received for debugging
    print(
        f"[_safe_json_loads] FAILED to parse (type={type(text).__name__}, "
        f"len={len(text)}, first 200 chars): {text[:200]!r}"
    )
    raise ValueError(
        f"Could not parse input as JSON. Received: {text[:100]}..."
    )


# ===========================================================================
# INFERENCE TOOLS
# ===========================================================================


def list_inference_cases() -> list[str]:
    """List all case IDs available for inference processing.

    Scans the exemplary_data/ directory for case folders that contain
    at least one PDF file (the input for the acting agent).

    Returns:
        Sorted list of case IDs (e.g., ["case_001", "case_002", ...]).
    """
    if not EXEMPLARY_DIR.exists():
        return []

    cases = []
    for folder in sorted(EXEMPLARY_DIR.iterdir()):
        if folder.is_dir() and any(folder.glob("*.pdf")):
            cases.append(folder.name)
    return cases


# ===========================================================================
# LEARNING TOOLS
# ===========================================================================


def list_cases() -> list[str]:
    """Return sorted list of all available case IDs.

    Scans agent_output/ for processed case folders.
    """
    return _case_loader.list_cases()


def load_case(case_id: str) -> dict:
    """Load all agent artifacts for a case and return structured summary.

    Args:
        case_id: The case identifier (folder name in data/agent_output/).

    Returns:
        dict with case_id, summary, decision, rejection_reason,
        rejection_phase, has_alf_output, and context.
    """
    case_data = _case_loader.run(case_id)
    _session_logger.log_case_loaded(case_id, case_data.summary)

    pp = case_data.postprocessing or {}
    inv_processing = pp.get("Invoice Processing", {})

    return {
        "case_id": case_data.case_id,
        "summary": case_data.summary,
        "decision": inv_processing.get("Invoice Status", "UNKNOWN"),
        "rejection_reason": inv_processing.get("Rejection Reason", ""),
        "rejection_phase": inv_processing.get("Rejection Phase", ""),
        "has_alf_output": case_data.alf_audit is not None,
        "context": case_data.context,
    }


def assess_impact(
    conditions_json: str, target_case_id: str, sample_size: str = "10"
) -> dict:
    """Evaluate proposed rule conditions against a sample of cases to detect unintended matches.

    The target case is always included. If total cases <= sample_size, all cases are evaluated.

    Args:
        conditions_json: JSON string of the conditions array from the proposed rule.
        target_case_id: The case ID the rule is intended to fix.
        sample_size: Max number of cases to evaluate (default 10). Set to a large number to evaluate all.

    Returns:
        dict with target_matched, collateral_matches, safe_cases, total_cases, sampled, sample_size, summary.
    """
    conditions = _safe_json_loads(conditions_json)
    report = _impact_assessor.run(
        conditions, target_case_id, sample_size=int(sample_size)
    )

    _session_logger.log_impact_assessed(
        report.summary,
        report.target_matched,
        len(report.collateral_matches),
        len(report.safe_cases),
        [m.case_id for m in report.collateral_matches],
    )

    return {
        "target_matched": report.target_matched,
        "collateral_matches": [
            {
                "case_id": m.case_id,
                "current_decision": m.decision,
                "rejection_reason": m.rejection_reason,
            }
            for m in report.collateral_matches
        ],
        "safe_cases": report.safe_cases,
        "total_cases": report.total_cases,
        "sampled": report.sampled,
        "sample_size": report.sample_size,
        "summary": report.summary,
    }


def validate_rule(rule_json: str) -> list[str]:
    """Validate rule schema against ALF requirements.

    Args:
        rule_json: JSON string of the rule dict.

    Returns:
        List of error strings. Empty list means the rule is valid.
    """
    return _rule_writer.validate_rule(_safe_json_loads(rule_json))


def check_conflicts(rule_json: str) -> list[str]:
    """Check for conflicts between proposed rule and existing rules.

    Args:
        rule_json: JSON string of the rule dict.

    Returns:
        List of warning strings. Empty list means no conflicts.
    """
    return _rule_writer.check_conflicts(_safe_json_loads(rule_json))


def write_rule(rule_json: str, mode: str = "add") -> dict:
    """Write a validated rule to rule_base.json.

    Args:
        rule_json: JSON string of the rule dict.
        mode: "add" for new rule, "update" to replace existing by ID.

    Returns:
        dict with success, rule_id, backup_path, total_rules, message.
    """
    result = _rule_writer.run(_safe_json_loads(rule_json), mode=mode)
    if result.success:
        _session_logger.log_rule_written(
            result.rule_id, result.backup_path, result.total_rules
        )
    return {
        "success": result.success,
        "rule_id": result.rule_id,
        "backup_path": result.backup_path,
        "total_rules": result.total_rules,
        "message": result.message,
    }


def delete_rule(rule_id: str) -> dict:
    """Delete a rule from rule_base.json by its ID.

    Creates a backup before deleting. The SME must confirm the deletion.

    Args:
        rule_id: The ALF rule ID to delete (e.g., "ALF-001").

    Returns:
        dict with success, rule_id, backup_path, total_rules, message.
    """
    result = _rule_writer.delete_rule(rule_id)
    if result.success:
        _session_logger.log_rule_written(
            result.rule_id, result.backup_path, result.total_rules
        )
    return {
        "success": result.success,
        "rule_id": result.rule_id,
        "backup_path": result.backup_path,
        "total_rules": result.total_rules,
        "message": result.message,
    }


def get_existing_rules() -> list[dict]:
    """Return all current ALF rules from rule_base.json."""
    return _rule_writer.get_existing_rules()


def get_existing_scopes() -> dict:
    """Return scope -> [rule_id, ...] mapping for mutual exclusion awareness."""
    return _rule_writer.get_existing_scopes()


def format_rule_display(rule_json: str) -> str:
    """Format a rule dict for human-readable display.

    Args:
        rule_json: JSON string of the rule dict.

    Returns:
        Formatted string for display to the SME.
    """
    try:
        rule_dict = _safe_json_loads(rule_json)
    except (json.JSONDecodeError, ValueError):
        return (
            "ERROR: Could not parse rule JSON. Please use get_existing_rules() "
            "to retrieve rules as structured data, then pass the JSON directly."
        )
    return _rule_writer.format_rule_display(rule_dict)


def get_next_rule_id() -> str:
    """Get the next available ALF rule ID (ALF-NNN format)."""
    return _rule_writer.next_rule_id()


def build_rule_discovery_context(case_id: str, sme_feedback: str) -> dict:
    """Build the complete context needed for LLM rule discovery.

    Args:
        case_id: The case identifier.
        sme_feedback: The SME's natural language description of what should change.

    Returns:
        dict with task_prompt and context fields for rule discovery.
    """
    case_data = _case_loader.run(case_id)
    _session_logger.log_sme_feedback(sme_feedback)

    pp = case_data.postprocessing or {}
    inv_processing = pp.get("Invoice Processing", {})
    failing_phase = inv_processing.get("Rejection Phase", "")
    agent_decision = inv_processing.get("Invoice Status", "UNKNOWN")
    rejection_reason = inv_processing.get("Rejection Reason", "")

    existing_rules = _rule_writer.get_existing_rules()
    existing_scopes = _rule_writer.get_existing_scopes()
    next_rule_id = _rule_writer.next_rule_id()

    rules_book_context = ""
    if RULES_BOOK_PATH.exists():
        rules_book_text = RULES_BOOK_PATH.read_text(encoding="utf-8")
        rules_book_context = extract_relevant_rules_book_sections(
            rules_book_text, failing_phase
        )

    validation_details = ""
    for phase_key in ["phase1", "phase2", "phase3", "phase4"]:
        phase_data = case_data.artifacts.get(phase_key, {})
        if phase_data and phase_data.get("validations"):
            validation_details += f"\n--- {phase_key.upper()} ---\n"
            for v in phase_data["validations"]:
                status = v.get("status", v.get("result", ""))
                step = v.get("step", v.get("step_name", ""))
                validation_details += f"  Step {step}: {status}\n"
                if v.get("rejection_template"):
                    validation_details += (
                        f"    Template: {v['rejection_template']}\n"
                    )

    invoice_json = json.dumps(
        case_data.context.get("invoice", {}), indent=2, default=str
    )[:3000]
    extraction_json = json.dumps(
        case_data.artifacts.get("extraction", {}), indent=2, default=str
    )[:3000]

    task_prompt = (
        RULE_DISCOVERY_SYSTEM_PROMPT
        + "\n\n"
        + RULE_DISCOVERY_TASK_TEMPLATE.format(
            sme_feedback=sme_feedback,
            case_id=case_id,
            agent_decision=agent_decision,
            rejection_reason=rejection_reason,
            failing_phase=failing_phase,
            case_summary=case_data.summary[:2000],
            validation_details=validation_details[:2000],
            invoice_json=invoice_json,
            extraction_json=extraction_json,
            existing_rules_json=json.dumps(
                existing_rules, indent=2, default=str
            )[:4000],
            existing_scopes=json.dumps(existing_scopes, indent=2),
            rules_book_context=rules_book_context[:4000],
            next_rule_id=next_rule_id,
        )
    )

    return {
        "task_prompt": task_prompt,
        "case_id": case_id,
        "agent_decision": agent_decision,
        "rejection_reason": rejection_reason,
        "failing_phase": failing_phase,
        "next_rule_id": next_rule_id,
    }


def build_rule_revision_context(
    case_id: str,
    current_rule_json: str,
    revision_feedback: str,
    impact_summary: str,
) -> dict:
    """Build context for LLM rule revision.

    Args:
        case_id: The case identifier.
        current_rule_json: JSON string of the current proposed rule.
        revision_feedback: SME's revision request.
        impact_summary: Summary from the impact assessment.

    Returns:
        dict with task_prompt for rule revision.
    """
    case_data = _case_loader.run(case_id)
    _session_logger.log_sme_revision(revision_feedback)
    current_rule = _safe_json_loads(current_rule_json)

    invoice_json = json.dumps(
        case_data.context.get("invoice", {}), indent=2, default=str
    )[:3000]
    extraction_json = json.dumps(
        case_data.artifacts.get("extraction", {}), indent=2, default=str
    )[:3000]

    task_prompt = RULE_REVISION_TASK_TEMPLATE.format(
        revision_feedback=revision_feedback,
        current_rule_json=json.dumps(current_rule, indent=2),
        impact_summary=impact_summary,
        case_id=case_id,
        case_summary=case_data.summary[:2000],
        invoice_json=invoice_json,
        extraction_json=extraction_json,
        rule_id=current_rule.get("id", "ALF-???"),
    )

    return {
        "task_prompt": task_prompt,
        "case_id": case_id,
        "rule_id": current_rule.get("id"),
    }


def discover_safe_rule(case_id: str, sme_feedback: str) -> dict:
    """Generate a new ALF rule with automatic safety validation.

    This tool handles the full rule discovery pipeline:
    1. Generates a rule via LLM based on case data and SME feedback
    2. Validates the rule schema
    3. Assesses impact across all existing cases
    4. If collateral matches are found, automatically tightens conditions
       and re-assesses (up to 3 attempts)

    Args:
        case_id: The case identifier the rule is intended to fix.
        sme_feedback: The SME's natural language description of what should change.

    Returns:
        dict with: success, rule (dict), rule_json (string), display (formatted),
        impact (assessment results), attempts, revision_log, has_collateral,
        collateral_warning.
    """
    _session_logger.log_sme_feedback(sme_feedback)
    result = _orchestrator.discover(case_id, sme_feedback)
    if result.get("success"):
        _session_logger._add_event(
            "rule_discovered",
            {
                "case_id": case_id,
                "rule_id": result["rule"].get("id", "?"),
                "attempts": result["attempts"],
                "has_collateral": result["has_collateral"],
            },
        )
    return result


def revise_safe_rule(
    case_id: str, current_rule_json: str, sme_feedback: str
) -> dict:
    """Revise a proposed rule based on SME feedback with automatic safety validation.

    Takes the SME's revision feedback, revises the rule via LLM, then runs
    the same safety loop as discover_safe_rule: validates, assesses impact,
    and auto-tightens if collateral is found.

    Args:
        case_id: The target case identifier.
        current_rule_json: JSON string of the current proposed rule to revise.
        sme_feedback: The SME's revision feedback describing what to change.

    Returns:
        Same format as discover_safe_rule.
    """
    current_rule = _safe_json_loads(current_rule_json)
    _session_logger.log_sme_revision(sme_feedback)
    result = _orchestrator.revise(case_id, current_rule, sme_feedback)
    if result.get("success"):
        _session_logger._add_event(
            "rule_revised",
            {
                "case_id": case_id,
                "rule_id": result["rule"].get("id", "?"),
                "attempts": result["attempts"],
                "has_collateral": result["has_collateral"],
            },
        )
    return result


def log_session_event(event_type: str, data_json: str = "{}") -> str:
    """Log an event to the session log for auditability.

    Args:
        event_type: The type of event to log.
        data_json: JSON string of event-specific data.

    Returns:
        Confirmation message.
    """
    _session_logger._add_event(event_type, _safe_json_loads(data_json))
    return f"Logged event: {event_type}"


def save_session() -> str:
    """Save the current session log and return the file path."""
    path = _session_logger.save()
    return f"Session saved: {path}" if path else "No session events to save."


# ===========================================================================
# EXCEPTION QUEUE TOOLS
# ===========================================================================


def ingest_exception_queue(file_paths) -> dict:
    """Load and parse AP exception queue from one or multiple CSV/JSON files or directories.

    Accepts either:
      - A single path string (file or directory)
      - A list of path strings

    Args:
        file_paths: Path(s) to the exception queue CSV or JSON files.

    Returns:
        dict with 'exceptions' (list of dicts mapped to canonical schema), 
        'total', 'field_names', and 'source_paths'.
    """
    import csv
    import json as _json
    from pathlib import Path

    if isinstance(file_paths, str):
        file_paths = [file_paths]

    all_paths = []
    for fp in file_paths:
        path = Path(fp)
        if not path.is_absolute():
            path = EXEMPLARY_DIR / fp
            
        if path.is_dir():
            all_paths.extend(list(path.glob("*.csv")) + list(path.glob("*.json")))
        elif path.exists():
            all_paths.append(path)
            
    if not all_paths:
        return {
            "success": False,
            "error": "No valid files found to ingest.",
            "exceptions": [],
            "total": 0,
        }

    all_exceptions = []
    source_paths = []
    
    try:
        for path in all_paths:
            suffix = path.suffix.lower()
            if suffix == ".json":
                with open(path, encoding="utf-8") as f:
                    data = _json.load(f)
                raw_rows = data if isinstance(data, list) else data.get("exceptions", [])
            elif suffix == ".csv":
                with open(path, encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    raw_rows = [row for row in reader]
            else:
                continue
                
            if not raw_rows:
                continue
                
            source_paths.append(str(path))
            
            # Map headers for this specific file
            raw_headers = list(raw_rows[0].keys())
            mapping = _schema_mapper.map_headers(raw_headers)
            
            for row in raw_rows:
                mapped_row = {}
                for raw_key, raw_val in row.items():
                    canonical_key = mapping.get(raw_key)
                    if canonical_key:
                        mapped_row[canonical_key] = raw_val
                all_exceptions.append(mapped_row)

        return {
            "success": True,
            "exceptions": all_exceptions,
            "total": len(all_exceptions),
            "field_names": list(all_exceptions[0].keys()) if all_exceptions else [],
            "source_paths": source_paths,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "exceptions": [],
            "total": 0,
        }


def classify_exceptions(queue_json: str) -> dict:
    """Classify every exception in the queue using Gemini Pro.

    For each exception determines: primary_type, root_cause_hypothesis,
    severity (High/Medium/Low), confidence score, and recommended_action.

    Args:
        queue_json: JSON string of the exceptions list
                    (as returned by ingest_exception_queue).

    Returns:
        dict with 'classifications' (list of dicts) and 'summary'.
    """
    exceptions = _safe_json_loads(queue_json)
    if isinstance(exceptions, dict):
        exceptions = exceptions.get("exceptions", [])

    # PRE-CLASSIFICATION DUPLICATE DETECTION PASS
    from collections import defaultdict
    from datetime import datetime

    # Step 1: Exact duplicate detection
    exact_groups = defaultdict(list)
    for exc in exceptions:
        key = (
            str(exc.get("vendor_name", "")).strip().lower(),
            str(exc.get("invoice_number", "")).strip().lower(),
            str(exc.get("invoice_amount", "")).strip(),
            str(exc.get("currency", "")).strip().lower(),
            str(exc.get("po_number", "")).strip().lower(),
            str(exc.get("invoice_date", "")).strip().lower(),
        )
        exact_groups[key].append(exc)

    exact_duplicate_ids = set()
    pre_classifications = []

    for key, group in exact_groups.items():
        if len(group) > 1:
            for exc in group:
                iid = exc.get("invoice_id")
                exact_duplicate_ids.add(iid)
                pre_classifications.append({
                    "invoice_id": iid,
                    "primary_type": "Exact Duplicate Invoice",
                    "root_cause_hypothesis": "Pre-classification detected exact duplicate in the current batch.",
                    "recommended_action": "Reject duplicate invoice.",
                    "evidence_used": f"Matched {len(group)} invoices exactly on vendor, invoice number, amount, currency, PO, and date.",
                    "missing_data": [],
                    "evidence_checked": "Batch internal check",
                    "business_rule_triggered": "Pre-classification exact duplicate pass",
                    "raw_exception_type": exc.get("exception_type", "Other"),
                    "success": True,
                    "error": "",
                    "confidence": 1.00
                })

    # Step 2: Potential duplicate detection
    potential_groups = defaultdict(list)
    for exc in exceptions:
        iid = exc.get("invoice_id")
        if iid in exact_duplicate_ids:
            continue
        key = (
            str(exc.get("vendor_name", "")).strip().lower(),
            str(exc.get("po_number", "")).strip().lower(),
            str(exc.get("invoice_amount", "")).strip(),
            str(exc.get("currency", "")).strip().lower(),
        )
        potential_groups[key].append(exc)

    potential_duplicate_ids = set()
    for key, group in potential_groups.items():
        if len(group) > 1:
            valid_group = []
            for exc in group:
                try:
                    d = datetime.strptime(str(exc.get("invoice_date", "")).strip(), "%Y-%m-%d").date()
                    valid_group.append((d, exc))
                except ValueError:
                    pass
            valid_group.sort(key=lambda x: x[0])

            for i in range(len(valid_group)):
                for j in range(i+1, len(valid_group)):
                    d1, exc1 = valid_group[i]
                    d2, exc2 = valid_group[j]
                    if abs((d2 - d1).days) <= 7 and str(exc1.get("invoice_number")).strip().lower() != str(exc2.get("invoice_number")).strip().lower():
                        potential_duplicate_ids.add(exc1.get("invoice_id"))
                        potential_duplicate_ids.add(exc2.get("invoice_id"))

    # ── Historical duplicate detection (ERP Lookup) ──
    import json
    erp_path = EXEMPLARY_DIR / "exception_queue" / "erp_database.json"
    if erp_path.exists():
        with open(erp_path, 'r', encoding='utf-8') as f:
            erp_database = json.load(f)
    else:
        erp_database = {}
        
    historical_invoices = erp_database.get("historical_invoices", [])
    for exc in exceptions:
        iid = exc.get("invoice_id")
        if iid in potential_duplicate_ids or iid in exact_duplicate_ids:
            continue
            
        vendor = str(exc.get("vendor_name", "")).strip().lower()
        try:
            amt = float(exc.get("invoice_amount", 0))
        except ValueError:
            amt = -1.0
        po = str(exc.get("po_number", "")).strip().lower()
        inv_date_str = str(exc.get("invoice_date", "")).strip()
        
        if not po: # Needs PO for this specific check
            continue
            
        try:
            inv_date = datetime.strptime(inv_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
            
        for hist in historical_invoices:
            h_vendor = str(hist.get("vendor_name", "")).strip().lower()
            try:
                h_amt = float(hist.get("invoice_amount", 0))
            except ValueError:
                h_amt = -2.0
            h_po = str(hist.get("po_number", "")).strip().lower()
            h_date_str = str(hist.get("invoice_date", "")).strip()
            
            # If historical invoice doesn't have PO/date, we skip this specific 7-day PO check, 
            # though it might be caught by other duplicate checks if it was an exact match.
            if h_vendor == vendor and h_amt == amt and h_po == po and h_date_str:
                try:
                    h_date = datetime.strptime(h_date_str, "%Y-%m-%d").date()
                    if abs((inv_date - h_date).days) <= 7:
                        potential_duplicate_ids.add(iid)
                        pre_classifications.append({
                            "invoice_id": iid,
                            "primary_type": "Potential Duplicate Invoice",
                            "root_cause_hypothesis": "Historical ERP lookup detected potential duplicate.",
                            "recommended_action": "Verify if this is a duplicate submission of a recently processed invoice.",
                            "evidence_used": f"Matched historical invoice {hist.get('invoice_number', 'UNKNOWN')} on vendor, PO, and amount within 7 days.",
                            "missing_data": [],
                            "evidence_checked": "ERP historical_invoices",
                            "business_rule_triggered": "Pre-classification historical duplicate pass",
                            "raw_exception_type": exc.get("exception_type", "Other"),
                            "success": True,
                            "error": "",
                            "confidence": 0.85
                        })
                        break
                except ValueError:
                    pass

    # ── Processed Invoices Duplicate Check ──
    processed_invoices = erp_database.get("processed_invoices", {})
    for exc in exceptions:
        iid = exc.get("invoice_id")
        if iid in potential_duplicate_ids or iid in exact_duplicate_ids:
            continue
            
        po = str(exc.get("po_number", "")).strip().upper()
        if not po or po not in processed_invoices:
            continue
            
        try:
            amt = float(exc.get("invoice_amount", 0))
        except ValueError:
            amt = -1.0
            
        inv_date_str = str(exc.get("invoice_date", "")).strip()
        try:
            inv_date = datetime.strptime(inv_date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
            
        for p_inv in processed_invoices[po]:
            try:
                p_amt = float(p_inv.get("amount", 0))
            except ValueError:
                p_amt = -2.0
                
            p_date_str = str(p_inv.get("date", "")).strip()
            
            if p_amt == amt and p_date_str:
                try:
                    p_date = datetime.strptime(p_date_str, "%Y-%m-%d").date()
                    if abs((inv_date - p_date).days) <= 7:
                        potential_duplicate_ids.add(iid)
                        pre_classifications.append({
                            "invoice_id": iid,
                            "primary_type": "Potential Duplicate Invoice",
                            "root_cause_hypothesis": "Recently processed invoice detected for the same PO and amount within 7 days.",
                            "recommended_action": "Verify if this is a duplicate submission of a recently processed invoice.",
                            "evidence_used": f"Matched processed invoice {p_inv.get('invoice_number', 'UNKNOWN')} on PO and amount within 7 days.",
                            "missing_data": [],
                            "evidence_checked": "ERP processed_invoices",
                            "business_rule_triggered": "Pre-classification processed invoice duplicate pass",
                            "raw_exception_type": exc.get("exception_type", "Other"),
                            "success": True,
                            "error": "",
                            "confidence": 0.85
                        })
                        break
                except ValueError:
                    pass

    for exc in exceptions:
        iid = exc.get("invoice_id")
        if iid in potential_duplicate_ids and iid not in exact_duplicate_ids:
            pre_classifications.append({
                "invoice_id": iid,
                "primary_type": "Potential Duplicate Invoice",
                "root_cause_hypothesis": "Pre-classification detected potential duplicate in the current batch (similar dates, diff invoice numbers).",
                "recommended_action": "Verify if this is a duplicate submission under a different number.",
                "evidence_used": "Matched another invoice on vendor, PO, amount, currency, and date within 3 days.",
                "missing_data": [],
                "evidence_checked": "Batch internal check",
                "business_rule_triggered": "Pre-classification potential duplicate pass",
                "raw_exception_type": exc.get("exception_type", "Other"),
                "success": True,
                "error": "",
                "confidence": 0.85
            })

    # Only invoices that pass both checks go to the LLM classifier
    to_classify = [
        exc for exc in exceptions 
        if exc.get("invoice_id") not in exact_duplicate_ids 
        and exc.get("invoice_id") not in potential_duplicate_ids
    ]

    # Load Mock ERP Database Context
    erp_db_path = EXEMPLARY_DIR / "exception_queue" / "erp_database.json"
    erp_context = {}
    if erp_db_path.exists():
        try:
            with open(erp_db_path, "r", encoding="utf-8") as f:
                erp_context = json.load(f)
        except Exception as e:
            print(f"Failed to load ERP context: {e}")

    # Load Phase 1 Master Rules
    master_rules_path = AGENT_PKG_DIR / "shared_libraries" / "invoice_master_data.yaml"
    master_rules = {}
    if master_rules_path.exists():
        try:
            import yaml
            with open(master_rules_path, "r", encoding="utf-8") as f:
                master_rules = yaml.safe_load(f)
        except Exception as e:
            print(f"Failed to load Phase 1 master rules: {e}")

    results = _exception_classifier.classify_batch(to_classify, erp_context=erp_context, master_rules=master_rules)

    classifications = pre_classifications + [
        {
            "invoice_id": r.invoice_id,
            "primary_type": r.primary_type,
            "root_cause_hypothesis": r.root_cause_hypothesis,
            "recommended_action": r.recommended_action,
            "evidence_used": r.evidence_used,
            "missing_data": r.missing_data,
            "evidence_checked": r.evidence_checked,
            "business_rule_triggered": r.business_rule_triggered,
            "raw_exception_type": r.raw_exception_type,
            "success": r.success,
            "error": r.error,
            "confidence": getattr(r, "confidence", 0.0),
        }
        for r in results
    ]

    summary = {
        "total": len(classifications),
        "successful": sum(1 for c in classifications if c["success"]),
        "by_type": {},
    }
    for c in classifications:
        t = c["primary_type"]
        summary["by_type"][t] = summary["by_type"].get(t, 0) + 1

    return {"classifications": classifications, "summary": summary}


def assign_resolution_paths(classified_json: str) -> dict:
    """Deterministically assign a resolution path to each classified exception.

    No LLM involved. Applies rules from exception_resolution_rules.yaml.

    Args:
        classified_json: JSON string of the classified exceptions dict
                         (as returned by classify_exceptions).

    Returns:
        dict with 'invoices' (list of dicts) and 'summary'.
    """
    data = _safe_json_loads(classified_json)

    # Support being called with the full classify output or just the lists
    exceptions = data.get("exceptions", [])
    classifications = data.get("classifications", [])

    if not exceptions and not classifications:
        return {
            "success": False,
            "error": "Input must contain 'exceptions' and 'classifications' lists.",
            "invoices": [],
        }

    from invoice_processing.core.exception_classifier import ExceptionClassification
    parsed_classifications = [
        ExceptionClassification(**c) if isinstance(c, dict) else c 
        for c in classifications
    ]

    results = _resolution_router.assign_batch(exceptions, parsed_classifications)

    invoices = [r.to_dict() for r in results]

    summary = {
        "total_invoices": len(invoices),
        "payments_blocked": sum(1 for r in invoices if r["payment_blocked"]),
        "escalations_required": sum(1 for r in invoices if r["escalation_required"]),
    }

    return {"invoices": invoices, "summary": summary}


def draft_communications(resolved_json: str) -> dict:
    """Draft vendor or internal communications for exceptions that require them.

    Args:
        resolved_json: JSON string containing 'invoices'

    Returns:
        dict with 'communications' (dict mapping invoice_id to text) and 'summary'.
    """
    data = _safe_json_loads(resolved_json)
    invoices = data.get("invoices", [])

    if not invoices:
        return {
            "success": False,
            "error": "Input must contain 'invoices' list.",
            "communications": {},
            "summary": {"total": 0, "drafted": 0},
        }

    # Since drafting isn't fully updated yet, we will mock communication drafts
    # for any invoice that has escalation_required.
    communications = {}
    drafted = 0
    for inv in invoices:
        if inv.get("escalation_required"):
            communications[inv["invoice_id"]] = f"Drafted communication for {inv['invoice_id']} regarding escalations."
            drafted += 1

    summary = {
        "total": len(invoices),
        "drafted": drafted
    }

    return {"communications": communications, "summary": summary}


def build_priority_output(all_stages_json: str) -> dict:
    """Assemble the final prioritised exception work queue and summary dashboard.

    Args:
        all_stages_json: JSON string containing 'invoices' and 'communications'.

    Returns:
        dict from queue formatter.
    """
    data = _safe_json_loads(all_stages_json)
    invoices_data = data.get("invoices", [])
    communications = data.get("communications", {})
    valid_invoices = data.get("valid_invoices", [])
    valid_invoices_count = data.get("valid_invoices_count", len(valid_invoices))

    if not invoices_data:
        return {
            "success": False,
            "error": "Input must contain invoices list.",
        }

    from invoice_processing.core.resolution_router import InvoiceResult
    from invoice_processing.core.exception_classifier import ExceptionClassification

    invoices = []
    for inv_d in invoices_data:
        # Reconstruct InvoiceResult
        excs = []
        for e in inv_d.get("final_exception_list", []):
            conf = e.pop("confidence", 0.0)
            exc_obj = ExceptionClassification(**e)
            exc_obj.confidence = conf
            excs.append(exc_obj)
        inv = InvoiceResult(
            invoice_id=inv_d["invoice_id"],
            invoice_amount=inv_d["invoice_amount"],
            invoice_age_days=inv_d["invoice_age_days"],
            vendor_name=inv_d.get("vendor_name", ""),
            invoice_number=inv_d.get("invoice_number", ""),
            final_exception_list=excs,
            priority_tier=inv_d.get("priority_tier", "LOW"),
            payment_blocked=inv_d["payment_blocked"],
            escalation_required=inv_d["escalation_required"],
            escalation_decision_reason=inv_d.get("escalation_decision_reason", ""),
            normalized_priority_score=inv_d.get("normalized_priority_score", 0.0),
            raw_priority_score=inv_d.get("raw_priority_score", 0.0),
            root_cause_categories=inv_d["root_cause_categories"],
            resolution_owners=inv_d["resolution_owners"],
            sla_hours=inv_d["sla_hours"],
            decision_trace=inv_d["decision_trace"],
            skipped_exceptions_trace=inv_d.get("skipped_exceptions_trace", []),
            auto_resolved=inv_d.get("auto_resolved", False),
            auto_close_flag=inv_d.get("auto_close_flag", False),
        )
        invoices.append(inv)

    return _queue_formatter.build(invoices, communications)

