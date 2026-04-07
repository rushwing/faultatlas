#!/usr/bin/env python3
"""
Seed sample log files into FaultAtlas to trigger the full ingestion pipeline.
Usage: uv run python scripts/seed_data.py
"""

import asyncio
import os

import httpx

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "changeme-local-dev")

SAMPLE_LOGS = [
    (
        "sample_oom.log",
        "text/plain",
        """\
2024-01-15T02:13:44Z WARN  kernel: Out of memory: Kill process 1234 (java) score 900
2024-01-15T02:13:44Z ERROR java.lang.OutOfMemoryError: Java heap space
2024-01-15T02:13:44Z ERROR     at java.util.Arrays.copyOf(Arrays.java:3210)
2024-01-15T02:13:44Z FATAL Service crashed. Restarting in 5s.
""",
    ),
    (
        "sample_network.log",
        "text/plain",
        """\
2024-01-15T03:00:01Z INFO  TCP connection established: 10.0.1.5:443 -> 10.0.2.8:8080
2024-01-15T03:00:02Z WARN  Retrying request (attempt 2/3): connection timeout to 10.0.2.8:8080
2024-01-15T03:00:07Z ERROR Circuit breaker OPEN for payment-gateway after 5 failures
2024-01-15T03:00:07Z ERROR HTTPSConnectionPool(host='payment-gateway', port=443): Max retries
""",
    ),
]


async def seed() -> None:
    async with httpx.AsyncClient(headers={"X-API-Key": API_KEY}, timeout=30.0) as client:
        for filename, content_type, content in SAMPLE_LOGS:
            response = None
            for attempt in range(1, 4):
                try:
                    response = await client.post(
                        f"{API_BASE}/documents",
                        files={"file": (filename, content.encode(), content_type)},
                    )
                    if response.status_code < 500:
                        break
                except httpx.HTTPError:
                    if attempt == 3:
                        raise
                await asyncio.sleep(attempt)

            if response is None:
                raise RuntimeError(f"failed to upload {filename}")
            response.raise_for_status()
            data = response.json()
            print(  # noqa: E501
                f"Uploaded {filename} -> document_id={data['document_id']} status={data['status']}"
            )

    print("\nSeed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
