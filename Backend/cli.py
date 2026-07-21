#!/usr/bin/env python
"""AP Exception Handling agent — command-line entry point.

Single command, single input, structured output. No server, no login.

    python cli.py examples/sample_exceptions.csv
    python cli.py path/to/exceptions.csv --out report.json
    python cli.py path/to/exceptions.csv --json          # full report to stdout

Runs fully offline in deterministic mock mode when no AI provider key is set
(see .env.example). Set ANTHROPIC_API_KEY to use real Claude classification.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.standalone import build_report, render_summary, run_pipeline_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ap-agent",
        description="Triage a queue of AP invoice exceptions from a CSV file.",
    )
    parser.add_argument(
        "csv",
        help="Path to the exception-queue CSV (see examples/sample_exceptions.csv).",
    )
    parser.add_argument(
        "-o",
        "--out",
        metavar="FILE",
        help="Write the full JSON report to FILE.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full JSON report to stdout instead of the text summary.",
    )
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        print(f"error: no such file: {csv_path}", file=sys.stderr)
        return 2

    state = run_pipeline_path(csv_path)
    report = build_report(state)

    if args.out:
        Path(args.out).write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(render_summary(report))
        if args.out:
            print(f"\nFull JSON report written to: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
