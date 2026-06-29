"""AP Exception Handling Agent - Main Entry Point.

Launches the Gradio dashboard with optional FastAPI backend.
Run with: python app.py
"""

import os
import sys
import threading
import argparse

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.logging_config import setup_logging
from config.settings import settings

logger = setup_logging("main")


def launch_api(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Launch the FastAPI server in a background thread.

    Args:
        host: Host address to bind the server.
        port: Port number for the API server.
    """
    import uvicorn
    from api import app

    logger.info(f"Starting FastAPI server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")


def main() -> None:
    """Main entry point for the AP Exception Handling Agent.

    Parses command-line arguments, optionally launches the FastAPI
    backend in a background thread, and starts the Gradio dashboard.
    """
    parser = argparse.ArgumentParser(
        description="AP Exception Handling Agent"
    )
    parser.add_argument(
        "--api",
        action="store_true",
        help="Also launch FastAPI server in background",
    )
    parser.add_argument(
        "--api-port",
        type=int,
        default=8000,
        help="FastAPI server port (default: 8000)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Gradio dashboard port (default: 7860)",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="Create a public Gradio sharing link",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("AP Exception Handling Agent v1.0.0")
    logger.info("=" * 60)
    logger.info(f"Demo Mode: {settings.DEMO_MODE}")
    logger.info(f"LLM Available: {settings.is_llm_available}")
    logger.info(f"Model: {settings.MODEL_NAME}")

    # Optionally launch FastAPI in background
    if args.api:
        api_thread = threading.Thread(
            target=launch_api,
            args=("0.0.0.0", args.api_port),
            daemon=True,
        )
        api_thread.start()
        logger.info(
            f"FastAPI docs available at http://localhost:{args.api_port}/docs"
        )

    # Launch Gradio dashboard
    from ui.dashboard import create_dashboard, THEME, CUSTOM_CSS

    dashboard = create_dashboard()

    logger.info(f"Launching Gradio dashboard on port {args.port}")
    dashboard.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share,
        show_error=True,
        theme=THEME,
        css=CUSTOM_CSS,
    )


if __name__ == "__main__":
    main()
