"""
demo.py — auxilab-agent-ap-exceptions

Runs the full 5-step AP Exception Queue pipeline on the bundled sample data
and prints a formatted summary to stdout.

No dashboard, no server, no login required.

Usage:
    # With a real API key:
    LLM_PROVIDER=gemini GEMINI_API_KEY=your_key python demo.py

    # With Claude:
    LLM_PROVIDER=claude ANTHROPIC_API_KEY=your_key python demo.py

    # With no API key (demo stub responses):
    DEMO_MODE=true python demo.py
"""

import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------

AGENT_DIR = Path(__file__).parent / "python" / "agents" / "invoice-processing"
SAMPLE_CSV = (
    AGENT_DIR
    / "invoice_processing"
    / "exemplary_data"
    / "exception_queue"
    / "exception_queue.csv"
)

# Add agent package to path so imports work without installing
sys.path.insert(0, str(AGENT_DIR))

# Load .env if present
try:
    from dotenv import load_dotenv  # noqa: PLC0415

    env_file = AGENT_DIR / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        load_dotenv()
except ImportError:
    pass  # dotenv optional in minimal environments


# ---------------------------------------------------------------------------
# Colour helpers (plain fallback when terminal has no colour support)
# ---------------------------------------------------------------------------

_BOLD = "\033[1m"
_RED = "\033[31m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_CYAN = "\033[36m"
_RESET = "\033[0m"

_COLOUR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}" if _COLOUR else text


def _header(text: str) -> None:
    width = 70
    print()
    print(_c(_BOLD, "=" * width))
    print(_c(_BOLD, f"  {text}"))
    print(_c(_BOLD, "=" * width))


def _section(text: str) -> None:
    print()
    print(_c(_CYAN, f"── {text}"))


def _tier_colour(tier: str) -> str:
    colours = {"HIGH": _RED, "MEDIUM": _YELLOW, "LOW": _GREEN}
    return colours.get(tier, "")


# ---------------------------------------------------------------------------
# Main demo
# ---------------------------------------------------------------------------


def main() -> None:
    provider = os.getenv("LLM_PROVIDER", "gemini")
    demo_mode = os.getenv("DEMO_MODE", "false").lower() == "true"

    _header("AP Invoice Exception Queue — Demo")

    print(f"  Provider  : {_c(_BOLD, provider.upper())}")
    print(f"  Demo mode : {_c(_BOLD, str(demo_mode))}")
    print(f"  Input     : {SAMPLE_CSV.name} ({SAMPLE_CSV.stat().st_size // 1024} KB)")

    if not SAMPLE_CSV.exists():
        print(_c(_RED, f"\n[ERROR] Sample file not found: {SAMPLE_CSV}"))
        sys.exit(1)

    # ── Import pipeline steps ──────────────────────────────────────────────
    try:
        from invoice_processing.core.exception_classifier import ExceptionClassifier  # noqa: PLC0415
        from invoice_processing.core.resolution_router import ResolutionRouter  # noqa: PLC0415
        from invoice_processing.core.communication_drafter import CommunicationDrafter  # noqa: PLC0415
        from invoice_processing.core.queue_formatter import QueueFormatter  # noqa: PLC0415
        from invoice_processing.core.schema_mapper import SchemaMapper  # noqa: PLC0415
    except ImportError as e:
        print(_c(_RED, f"\n[ERROR] Missing dependency: {e}"))
        print("Run:  uv sync   or   pip install -r invoice_processing/requirements.txt")
        sys.exit(1)

    # ── Step 1: Ingest ─────────────────────────────────────────────────────
    _section("Step 1 — Ingest & Schema Map")
    import csv  # noqa: PLC0415

    with open(SAMPLE_CSV, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        raw_headers = reader.fieldnames or []
        rows = list(reader)

    mapper = SchemaMapper()
    mapping = mapper.map_headers(raw_headers)
    exceptions = []
    for row in rows:
        mapped = {mapping.get(k, k): v for k, v in row.items()}
        exceptions.append(mapped)

    print(f"  {len(exceptions)} invoices loaded, {len(raw_headers)} columns mapped")

    # Load ERP database
    erp_path = AGENT_DIR / "invoice_processing" / "exemplary_data" / "exception_queue" / "erp_database.json"
    erp_db = json.loads(erp_path.read_text(encoding="utf-8")) if erp_path.exists() else {}

    # ── Step 2: Classify ───────────────────────────────────────────────────
    _section("Step 2 — Classify Exceptions (LLM)")
    classifier = ExceptionClassifier()
    classifications = classifier.classify_batch(exceptions, erp_db)
    print(f"  {len(classifications)} invoices classified")

    # ── Step 3: Route ──────────────────────────────────────────────────────
    _section("Step 3 — Assign Resolution Paths (deterministic)")
    router = ResolutionRouter()
    resolutions = router.assign_batch(exceptions, classifications)
    print(f"  {len(resolutions)} resolution paths assigned")

    # ── Step 4: Draft Communications ───────────────────────────────────────
    _section("Step 4 — Draft Communications (LLM)")
    drafter = CommunicationDrafter()
    communications = drafter.draft_batch(exceptions, classifications, resolutions)
    drafted_count = sum(1 for c in communications if c.get("success") and c.get("draft"))
    print(f"  {drafted_count} communications drafted")

    # ── Step 5: Build Output ───────────────────────────────────────────────
    _section("Step 5 — Build Priority Queue")
    formatter = QueueFormatter()
    output = formatter.build(exceptions, classifications, resolutions, communications)
    queue = output.get("priority_queue", [])
    dashboard = output.get("dashboard", {})
    bv = dashboard.get("business_value_metrics", {})

    # ── Dashboard summary ──────────────────────────────────────────────────
    _header("Results")

    print(f"  Total invoices      : {dashboard.get('total_invoices', len(exceptions))}")
    print(f"  Payments blocked    : {dashboard.get('payments_blocked', 0)}")
    print(f"  Escalations needed  : {dashboard.get('escalations_required', 0)}")
    print(f"  Auto-resolved       : {dashboard.get('auto_resolved_count', 0)}")
    print(f"  Blocked value       : ${bv.get('blocked_payment_value', 0):>12,.2f}")
    print(f"  Duplicate risk      : ${bv.get('potential_duplicate_payment_value', 0):>12,.2f}")
    print(f"  Valid invoice value : ${bv.get('valid_invoice_value', 0):>12,.2f}")

    # ── Priority queue ─────────────────────────────────────────────────────
    _section("Priority Queue (top 10)")
    for i, inv in enumerate(queue[:10], 1):
        tier = inv.get("priority_tier", "")
        colour = _tier_colour(tier)
        print(
            f"\n  {i:>2}. {_c(_BOLD, inv.get('invoice_id', '?'))} | "
            f"{inv.get('vendor_name', '')}"
        )
        print(
            f"      {_c(colour, tier)} (score {inv.get('normalized_priority_score', 0):.0f}) "
            f"| SLA {inv.get('sla_hours', '?')}h "
            f"| Blocked: {inv.get('payment_blocked', False)}"
        )
        for exc in inv.get("final_exception_list", []):
            conf = exc.get("confidence", 0)
            print(f"      └─ {exc.get('primary_type', '?')} ({conf*100:.0f}% confidence)")
            print(f"         {exc.get('root_cause_hypothesis', '')[:90]}")

    # ── Save output ────────────────────────────────────────────────────────
    out_path = AGENT_DIR / "invoice_processing" / "data" / "exception_output" / "demo_output.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")

    print()
    print(_c(_GREEN, f"  Full output saved to: {out_path.relative_to(AGENT_DIR)}"))
    print()


if __name__ == "__main__":
    main()
