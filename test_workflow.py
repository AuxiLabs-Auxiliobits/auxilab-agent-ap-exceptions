import sys
import os
import json

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from graph.workflow import run_workflow

def test():
    file_path = "synthetic_queue.json"
    print(f"Running workflow on {file_path}...")
    try:
        result = run_workflow(file_path)
        print("Workflow completed successfully.")
        print(f"Exceptions processed: {len(result.get('prioritized_queue', []))}")
        print(f"Errors: {len(result.get('errors', []))}")
        
        # Print a sample classification
        if result.get("classified_queue"):
            print("\nSample Classification:")
            sample = result["classified_queue"][0]
            print(json.dumps(sample.model_dump(), indent=2))
            
    except Exception as e:
        print(f"Workflow failed: {str(e)}")

if __name__ == "__main__":
    test()
