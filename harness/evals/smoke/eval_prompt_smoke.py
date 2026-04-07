from __future__ import annotations

import os
import sys

import httpx

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "changeme-local-dev")
QUERY = "Why is payment-processor failing with Java heap space errors?"


def main() -> int:
    hashes: set[str] = set()
    with httpx.Client(timeout=10.0, headers={"X-API-Key": API_KEY}) as client:
        for _ in range(20):
            response = client.get(f"{API_BASE}/debug/prompt", params={"query": QUERY})
            response.raise_for_status()
            hashes.add(response.json()["layer1_hash"])

    if len(hashes) != 1:
        print(f"Layer 1 drift detected: {sorted(hashes)}")
        return 1

    print(next(iter(hashes)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
