from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
API_KEY = os.getenv("API_KEY", "changeme-local-dev")


@pytest.mark.asyncio
async def test_phase1_flow() -> None:
    tmp_doc = Path("/tmp/faultatlas-phase1-flow.log")
    tmp_doc.write_text(
        "\n".join(
            [
                "2024-01-15T02:13:44Z WARN kernel: Out of memory",
                "2024-01-15T02:13:44Z ERROR java.lang.OutOfMemoryError: Java heap space",
                "2024-01-15T02:13:44Z FATAL payment-processor crashed",
            ]
        )
    )

    async with httpx.AsyncClient(timeout=60.0, headers={"X-API-Key": API_KEY}) as client:
        try:
            health = await client.get(f"{API_BASE}/health")
        except httpx.HTTPError:
            pytest.skip("Integration test requires live API/retriever services")
        ready = await client.get(f"{API_BASE}/ready")
        assert health.status_code == 200
        assert ready.status_code == 200

        empty_diag = await client.post(
            f"{API_BASE}/diagnose",
            json={"query": "Why is payment-processor failing with Java heap space errors?"},
        )
        assert empty_diag.status_code == 200
        assert empty_diag.json()["confidence"] == "low"

        with tmp_doc.open("rb") as fh:
            upload = await client.post(
                f"{API_BASE}/documents",
                files={"file": ("sample_oom.log", fh.read(), "text/plain")},
            )
        assert upload.status_code == 200
        upload_json = upload.json()
        assert upload_json["status"] == "indexed"

        status = await client.get(f"{API_BASE}/documents/{upload_json['document_id']}/status")
        assert status.status_code == 200
        assert status.json()["status"] == "indexed"

        prompt_hashes = set()
        for _ in range(5):
            prompt = await client.get(
                f"{API_BASE}/debug/prompt",
                params={"query": "Why is payment-processor failing with Java heap space errors?"},
            )
            assert prompt.status_code == 200
            prompt_hashes.add(prompt.json()["layer1_hash"])
        assert len(prompt_hashes) == 1

        diagnose = await client.post(
            f"{API_BASE}/diagnose",
            json={"query": "Why is payment-processor failing with Java heap space errors?"},
        )
        assert diagnose.status_code == 200
        diagnosis = diagnose.json()
        assert diagnosis["summary"]
        assert diagnosis["evidence"]

        query_alias = await client.post(
            f"{API_BASE}/query",
            json={"query": "Why is payment-processor failing with Java heap space errors?"},
        )
        assert query_alias.status_code == 200
        assert query_alias.json()["answer"]

        benchmark = await client.post(
            f"{API_BASE}/benchmark/run",
            json={"runs_per_condition": 1, "backend": "sglang"},
        )
        assert benchmark.status_code == 200
        benchmark_json = benchmark.json()
        assert benchmark_json["run_id"]
        assert "cold_start" in benchmark_json["conditions"]
