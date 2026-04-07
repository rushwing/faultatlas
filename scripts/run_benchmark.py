#!/usr/bin/env python3
import argparse
import json
import os
import sys

import httpx

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "changeme-local-dev")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=["openai", "sglang"])
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="Print the raw JSON response only")
    args = parser.parse_args()

    payload = {"runs_per_condition": args.runs}
    if args.backend:
        payload["backend"] = args.backend

    with httpx.Client(timeout=120.0, headers={"X-API-Key": API_KEY}) as client:
        response = client.post(f"{API_BASE}/benchmark/run", json=payload)
        response.raise_for_status()
        data = response.json()

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    print(f"run_id: {data['run_id']}")
    print(f"backend: {data['backend']}")
    print(f"model: {data['model']}")
    for name, summary in data["conditions"].items():
        print(
            f"{name}: mean_ttft_ms={summary['mean_ttft_ms']:.1f} "
            f"p95_ttft_ms={summary['p95_ttft_ms']:.1f} "
            f"mean_tokens_per_sec={summary['mean_tokens_per_sec']:.2f} "
            f"errors={summary['error_count']}"
        )
    print(data["hypothesis_result"]["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
