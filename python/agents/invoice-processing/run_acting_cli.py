import argparse
import json
import sys
import os
from pathlib import Path

# Ensure we're running from the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import the process_invoice function
from invoice_processing.shared_libraries.acting.general_invoice_agent import process_invoice

def main():
    parser = argparse.ArgumentParser(description="Run the Acting Agent (Validation) in the Terminal")
    parser.add_argument(
        "--case", 
        type=str,
        default="case_01_simple_match",
        help="The name of the exemplary_data folder to process (e.g., case_01_simple_match, case_03_missing_po)"
    )
    args = parser.parse_args()

    # Determine the absolute path to the case directory
    base_dir = Path(__file__).resolve().parent
    exemplary_dir = base_dir / "invoice_processing" / "exemplary_data"
    source_folder = exemplary_dir / args.case

    if not source_folder.exists():
        print(f"Error: Folder '{source_folder}' does not exist.")
        print(f"Available cases in {exemplary_dir}:")
        for f in exemplary_dir.iterdir():
            if f.is_dir() and "exception_queue" not in f.name:
                print(f"  - {f.name}")
        sys.exit(1)

    print(f"\n{'='*80}")
    print(f"STARTING VALIDATION AGENT ON: {args.case}")
    print(f"{'='*80}\n")
    
    print("Reading PDF, extracting fields, and validating against US Business Rules...\n")
    
    try:
        # Run the Phase 1 Acting Agent
        acting_result = process_invoice(source_folder)
        
        print("\n" + "="*80)
        print("VALIDATION COMPLETE")
        print("="*80)
        
        # Pretty print the final JSON output
        print("\nEXCEPTIONS FOUND:")
        print(json.dumps(acting_result, indent=2))
        
        if acting_result.get("exceptions"):
            print(f"\nThe AI Agent autonomously discovered {len(acting_result['exceptions'])} exceptions!")
        else:
            print("\nThe AI Agent validated everything and found NO exceptions. It perfectly matched the rules.")

    except Exception as e:
        print(f"\nError during Acting Agent execution: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
