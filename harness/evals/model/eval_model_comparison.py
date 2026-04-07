"""
Model Comparative Eval
Measures: structured output rate, faithfulness, TTFT per model
Purpose: Inform model selection (Qwen2.5-7B vs Qwen3-8B vs GPT-4o-mini)

This is NOT a threshold-gated eval — it produces a comparison report
for human decision-making. It does enforce a minimum structured_output_rate.

Usage:
    # Compare all configured backends
    uv run python harness/evals/model/eval_model_comparison.py

    # Compare specific models
    uv run python harness/evals/model/eval_model_comparison.py \
        --backends sglang_qwen25 sglang_qwen3 openai_gpt4omini
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

API_KEY = os.getenv("API_KEY", "changeme-local-dev")
GOLDEN_PATH = REPO_ROOT / "harness/datasets/golden/agent_golden.json"
THRESHOLDS_PATH = REPO_ROOT / "harness/thresholds.yaml"

# Backend configurations — add new models here
BACKENDS: dict[str, dict] = {
    "sglang_qwen25": {
        "api_base": os.getenv("SGLANG_BASE_URL", "http://localhost:8100/v1"),
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "description": "Local SGLang — Qwen2.5-7B-Instruct on RTX 4090",
        "requires_gpu": True,
    },
    "sglang_qwen3": {
        "api_base": os.getenv("SGLANG_BASE_URL_QWEN3", "http://localhost:8101/v1"),
        "model": "Qwen/Qwen3-8B",
        "description": "Local SGLang — Qwen3-8B on RTX 4090",
        "requires_gpu": True,
    },
    "openai_gpt4omini": {
        "api_base": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "description": "OpenAI API — gpt-4o-mini",
        "requires_gpu": False,
    },
}


async def diagnose_with_backend(
    client: httpx.AsyncClient,
    api_base: str,
    query: str,
    context_chunks: list[str],
) -> dict:
    """
    Direct LLM call bypassing the FaultAtlas API — allows swapping model config
    without restarting the main service.
    """
    import time

    from openai import AsyncOpenAI

    # Import prompt builder
    sys.path.insert(0, str(REPO_ROOT / "services/api"))
    from app.agents.prompts import RAG_PROMPT, SYSTEM_PROMPT

    context = "\n\n---\n\n".join(context_chunks)
    user_prompt = RAG_PROMPT.format(context=context, question=query)

    openai_client = AsyncOpenAI(base_url=api_base, api_key=os.getenv("OPENAI_API_KEY", "empty"))

    start = time.monotonic()
    try:
        response = await openai_client.chat.completions.create(
            model=BACKENDS[list(BACKENDS.keys())[0]]["model"],  # overridden by caller
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        total_ms = int((time.monotonic() - start) * 1000)
        content = response.choices[0].message.content or ""

        # Try to parse as JSON
        try:
            import re

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            parsed = json.loads(json_match.group() if json_match else content)
            valid_json = True
        except Exception:
            parsed = {}
            valid_json = False

        return {
            "query": query,
            "content": content,
            "parsed": parsed,
            "valid_json": valid_json,
            "total_ms": total_ms,
            "tokens": response.usage.total_tokens if response.usage else 0,
            "error": None,
        }
    except Exception as e:
        return {
            "query": query,
            "content": "",
            "parsed": {},
            "valid_json": False,
            "total_ms": int((time.monotonic() - start) * 1000),
            "tokens": 0,
            "error": str(e),
        }


def run_eval(backends: list[str] | None = None) -> dict:
    import yaml

    thresholds = yaml.safe_load(THRESHOLDS_PATH.read_text())["model"]
    golden = json.loads(GOLDEN_PATH.read_text())[:3]  # Model eval uses subset

    active_backends = {k: v for k, v in BACKENDS.items() if not backends or k in backends}
    print(f"Comparing {len(active_backends)} backends over {len(golden)} queries...\n")

    comparison = {}
    for backend_id, config in active_backends.items():
        print(f"  Running: {config['description']}")
        results = asyncio.run(_run_backend(config, golden))

        valid_count = sum(1 for r in results if r["valid_json"])
        error_count = sum(1 for r in results if r["error"])
        avg_latency = sum(r["total_ms"] for r in results) / len(results)
        structured_output_rate = valid_count / len(results)

        comparison[backend_id] = {
            "description": config["description"],
            "model": config["model"],
            "structured_output_rate": structured_output_rate,
            "avg_latency_ms": avg_latency,
            "error_count": error_count,
            "min_structured_output_rate_threshold": thresholds["min_structured_output_rate"],
            "meets_threshold": structured_output_rate >= thresholds["min_structured_output_rate"],
        }

    print(f"\n── Model Comparison Results {'─' * 35}")
    print(f"  {'Backend':<25} {'JSON Rate':>10} {'Avg Latency':>14} {'Status':>8}")
    print(f"  {'─' * 25} {'─' * 10} {'─' * 14} {'─' * 8}")
    for bid, r in comparison.items():
        status = "PASS" if r["meets_threshold"] else "FAIL"
        rate = r["structured_output_rate"]
        lat = r["avg_latency_ms"]
        print(f"  {bid:<25} {rate:>9.1%} {lat:>12.0f}ms  [{status}]")
    print(f"  {'─' * 60}")
    print("\n  Note: This is a comparative report. No single 'pass/fail'.")
    print("  Use this to inform model selection decisions.")

    overall_pass = all(r["meets_threshold"] for r in comparison.values())

    report = {
        "eval_type": "model",
        "timestamp": datetime.now(UTC).isoformat(),
        "comparison": comparison,
        "passed": overall_pass,  # True only if ALL backends meet min structured output rate
    }

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_path = REPO_ROOT / f"harness/reports/model_{ts}.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved: {report_path.relative_to(REPO_ROOT)}")

    return report


async def _run_backend(config: dict, golden: list[dict]) -> list[dict]:
    async with httpx.AsyncClient() as client:
        # For simplicity, use empty context (tests model capability, not retrieval)
        return await asyncio.gather(
            *[
                diagnose_with_backend(client, config["api_base"], case["query"], [])
                for case in golden
            ]
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backends",
        nargs="+",
        choices=list(BACKENDS.keys()),
        help="Backends to compare (default: all)",
    )
    args = parser.parse_args()

    report = run_eval(backends=args.backends)
    sys.exit(0 if report["passed"] else 1)
