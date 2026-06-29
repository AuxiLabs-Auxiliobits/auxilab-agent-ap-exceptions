import argparse
import json
import sys
import os
import warnings
from dotenv import load_dotenv

# Suppress Vertex AI SDK deprecation warnings to clean up terminal output
warnings.filterwarnings("ignore", category=UserWarning, module="vertexai")

# Ensure we're running from the correct directory so paths work
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Load the environment variables (like API keys) from .env
load_dotenv()

# Import the exception queue runner
from invoice_processing.agent import run_exception_queue

def main():
    parser = argparse.ArgumentParser(description="Run AP Exception Queue Pipeline directly from CLI")
    parser.add_argument(
        "--file", 
        nargs="+",
        default=["exception_queue/exception_queue.csv"],
        help="Path(s) to the exception queue CSV/JSON file(s) or directories"
    )
    parser.add_argument(
        "--debug", 
        action="store_true",
        help="Enable diagnostic mode to trace mapping, rule evaluations, and routing"
    )
    args = parser.parse_args()

    print(f"Starting AP Exception Queue Processing for: {args.file}")
    
    try:
        result = run_exception_queue(args.file, debug=args.debug)
        
        print("\n" + "="*80)
        print("PIPELINE COMPLETED SUCCESSFULLY")
        print("="*80)
        
        # Pretty print the final dashboard
        if "dashboard" in result:
            print("\nSUMMARY DASHBOARD:")
            print(json.dumps(result["dashboard"], indent=2))
            
        if "priority_queue" in result:
            print("\nALL INVOICES IN EXCEPTION QUEUE (SORTED BY PRIORITY):")
            for item in result["priority_queue"]:
                print(f"  - [{item['invoice_id']}] Amount: ${item['invoice_amount']} | Priority Tier: {item.get('priority_tier', 'LOW')} | Score: {item['normalized_priority_score']} | SLA: {item['sla_hours']}h")
                print(f"    Payment Blocked: {item['payment_blocked']} | Escalation Required: {item['escalation_required']}")
                if item.get('resolution_owners'):
                    print(f"    Resolution Owners: {', '.join(item['resolution_owners'])}")
                print(f"    Exceptions:")
                for exc in item.get('final_exception_list', []):
                    print(f"      * {exc['primary_type']} (Confidence: {exc.get('confidence', 0.0):.2f})")
                    if exc.get("evidence_used"):
                        print(f"        Evidence: {exc['evidence_used']}")
                    if exc.get("evidence_checked"):
                        print(f"        Checked: {exc['evidence_checked']}")
                    if exc.get("missing_data"):
                        print(f"        Missing Data: {', '.join(exc['missing_data'])}")
                if item.get("decision_trace"):
                    print(f"    Decision Trace:")
                    for trace in item['decision_trace']:
                        print(f"      - {trace}")
                print()
                
        if "output_path" in result:
            print(f"\nFull output saved to: {result['output_path']}")
            
    except Exception as e:
        print(f"\nError during pipeline execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
