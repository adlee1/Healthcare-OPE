#!/usr/bin/env python3
"""Collect private five-model pilot replies and factual metrics without API calls."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import secrets
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from april_repro.llm_run_summary import write_summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet-directory", action="append", required=True)
    parser.add_argument("--run-directory", action="append", default=[])
    parser.add_argument("--output-directory")
    args = parser.parse_args(argv)
    output = Path(args.output_directory) if args.output_directory else ROOT / "artifacts/llm-summaries" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4))
    try:
        summary = write_summary(args.packet_directory, args.run_directory, output)
        print(json.dumps({key: summary[key] for key in ("status", "unique_requests", "completed_annotations",
            "valid_predictions", "missing_predictions", "recorded_attempt_count", "automatic_retries")}
            | {"output_directory": str(output.resolve()), "external_calls": 0}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__,
                          "details": "Inspect local packet/run integrity; no API calls were made."}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
