import argparse
import json
import sys
import os
from pathlib import Path

# Ensure we're running from the correct directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Import run_inference
from invoice_processing.agent import run_inference

def main():
    parser = argparse.ArgumentParser(description="Run the single document inference pipeline (Acting -> Investigation -> ALF)")
    parser.add_argument(
        "--case", 
        type=str,
        required=True,
        help="The name of the exemplary_data folder to process (e.g., upload_abc123)"
    )
    args = parser.parse_args()

    # Determine the absolute path to the case directory
    base_dir = Path(__file__).resolve().parent
    exemplary_dir = base_dir / "invoice_processing" / "exemplary_data"
    source_folder = exemplary_dir / args.case

    if not source_folder.exists():
        result = {
            "status": "ERROR",
            "error": f"Folder '{source_folder}' does not exist.",
            "pipeline_time": 0
        }
        print(json.dumps(result))
        sys.exit(1)

    try:
        # We redirect stdout so that the agent's print statements don't mess up our JSON output 
        # that the frontend is waiting for.
        # However, we can also just let the agent print to stdout, and the frontend will just show it.
        # But wait, `run_inference` returns a dictionary that we want to parse as JSON.
        # It's better to print a distinct delimiter before the JSON, or just redirect stdout.
        # Let's let the pipeline print to stderr instead, so only the final JSON is on stdout.
        
        # Save original stdout
        original_stdout = sys.stdout
        # Redirect stdout to stderr so we can see logs in UI, but keep stdout clean for JSON
        sys.stdout = sys.stderr

        result = run_inference(args.case)
        
        # Restore stdout to print the final JSON
        sys.stdout = original_stdout
        
        # Output the result as JSON
        print(json.dumps(result, indent=2, default=str))

    except Exception as e:
        sys.stdout = original_stdout
        result = {
            "status": "ERROR",
            "error": str(e),
            "pipeline_time": 0
        }
        print(json.dumps(result))
        sys.exit(1)

if __name__ == "__main__":
    main()
