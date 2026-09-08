#!/usr/bin/env python3
"""Pipeline Execution CLI Entrypoint.

Usage:
    python scripts/run_pipeline.py --env dev
    python scripts/run_pipeline.py --env prod
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline.runner import PipelineRunner


def main():
    parser = argparse.ArgumentParser(description="Execute Data Engineering Pipeline")
    parser.add_argument(
        "--env",
        type=str,
        default="dev",
        choices=["dev", "prod", "test"],
        help="Target runtime environment (default: dev)",
    )
    args = parser.parse_args()

    print(f"[*] Starting Pipeline Runner in '{args.env}' environment...")
    runner = PipelineRunner()
    result = runner.run(env=args.env)

    print("\n" + "=" * 60)
    print("                    PIPELINE EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Status:               {result.status}")
    print(f"Environment:          {result.environment}")
    print(f"Execution Duration:   {result.duration_seconds}s")
    print(f"Records Extracted:    {result.records_extracted}")
    print(f"Records Transformed:  {result.records_transformed}")
    print(f"Records Loaded:       {result.records_loaded}")
    print(f"Anomalies Flagged:    {result.anomalies_detected}")
    if result.output_destination:
        print(f"Output Target:        {result.output_destination}")
    if result.error_message:
        print(f"Error Message:        {result.error_message}")
    print("=" * 60)

    if result.status != "SUCCESS":
        sys.exit(1)


if __name__ == "__main__":
    main()
