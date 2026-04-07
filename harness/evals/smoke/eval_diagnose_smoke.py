from __future__ import annotations

import json
import os
import sys

import httpx

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "changeme-local-dev")


def main() -> int:
    with httpx.Client(timeout=30.0, headers={"X-API-Key": API_KEY}) as client:
        response = client.post(
            f"{API_BASE}/diagnose",
            json={"query": "Why is payment-processor failing with Java heap space errors?"},
        )
        response.raise_for_status()
        data = response.json()

    required = {
        "session_id",
        "summary",
        "suspected_causes",
        "evidence",
        "next_actions",
        "confidence",
        "latency_ms",
        "tokens_used",
        "prefix_cache_hint",
    }
    missing = required.difference(data)
    if missing:
        print(f"Missing fields: {sorted(missing)}")
        return 1
    if data["confidence"] not in {"low", "medium", "high"}:
        print("Invalid confidence value")
        return 1
    if not isinstance(data["evidence"], list):
        print("Evidence is not a list")
        return 1

    print(
        json.dumps(
            {"session_id": data["session_id"], "confidence": data["confidence"]},
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
