"""
Prompt Stability & Regression Eval
Measures:
  - layer1_stability: Layer 1 (system prompt) hash must be identical across N calls
  - regression: new prompt version must not drop RAGAS faithfulness > 5 points vs baseline

Usage:
    # Stability check only (fast)
    uv run python harness/evals/prompt/eval_prompt_stability.py --mode stability

    # Full regression (requires baseline saved first)
    uv run python harness/evals/prompt/eval_prompt_stability.py --mode regression \
        --baseline harness/reports/prompt_baseline_v1.json

    # Save current state as new baseline
    uv run python harness/evals/prompt/eval_prompt_stability.py --mode save-baseline \
        --version v1
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

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "changeme-local-dev")
THRESHOLDS_PATH = REPO_ROOT / "harness/thresholds.yaml"

# Queries used for stability testing — designed to produce different Layer 3 content
# while keeping Layer 1 (system) and Layer 2 (context) identical
STABILITY_QUERIES = [
    "Java OutOfMemoryError in payment service",
    "TCP timeout in order processing",
    "Service restart loop with high memory",
    "Circuit breaker opened on payment gateway",
    "Heap dump shows large cache object",
]


def load_thresholds() -> dict:
    import yaml

    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)["prompt"]


async def fetch_prompt_debug(client: httpx.AsyncClient, query: str) -> dict:
    """
    Call a debug endpoint that returns the assembled prompt layers.
    If the endpoint doesn't exist yet, extract from diagnosis response metadata.

    Note: This requires adding a debug endpoint to the API service:
    GET /debug/prompt?query=...  → { layer1_hash, layer2_hash, layer3_preview }
    """
    resp = await client.get(
        f"{API_BASE}/debug/prompt",
        params={"query": query},
        headers={"X-API-Key": API_KEY},
    )
    resp.raise_for_status()
    return resp.json()


async def run_stability_check(runs: int = 20) -> dict:
    """
    Call the prompt debug endpoint N times with different queries.
    Assert Layer 1 hash is identical across all calls.
    """
    print(f"Running Layer 1 stability check ({runs} calls)...")
    hashes = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        queries = (STABILITY_QUERIES * (runs // len(STABILITY_QUERIES) + 1))[:runs]
        for i, query in enumerate(queries):
            try:
                data = await fetch_prompt_debug(client, query)
                hashes.append(data["layer1_hash"])
                if i % 5 == 0:
                    print(f"  Run {i + 1}/{runs}: layer1_hash={data['layer1_hash'][:12]}...")
            except Exception as e:
                print(f"  Run {i + 1} FAILED: {e}")
                hashes.append(f"ERROR:{e}")

    unique_hashes = set(hashes)
    stable = len(unique_hashes) == 1
    error_count = sum(1 for h in hashes if h.startswith("ERROR:"))

    print(f"\n  Unique Layer 1 hashes: {len(unique_hashes)}")
    if not stable:
        print(f"  DRIFT DETECTED: {unique_hashes}")

    return {
        "stable": stable,
        "runs": runs,
        "unique_hashes": list(unique_hashes),
        "error_count": error_count,
        "score": 1.0 if stable else 0.0,
    }


def compare_to_baseline(current_scores: dict, baseline_path: Path) -> dict:
    """Compare current faithfulness score to saved baseline."""
    baseline = json.loads(baseline_path.read_text())
    if baseline.get("placeholder") is True:
        return {
            "baseline_faithfulness": baseline.get("faithfulness"),
            "current_faithfulness": current_scores.get("faithfulness", 0.0),
            "delta": None,
            "threshold": None,
            "passed": True,
            "skipped": True,
            "verdict": (
                "Baseline is marked as placeholder; skipping prompt regression comparison "
                "until a real baseline is generated."
            ),
        }

    baseline_faithfulness = baseline.get("faithfulness", 0.0)
    current_faithfulness = current_scores.get("faithfulness", 0.0)
    delta = current_faithfulness - baseline_faithfulness

    import yaml

    thresholds = yaml.safe_load(THRESHOLDS_PATH.read_text())["prompt"]
    threshold = thresholds.get("regression_threshold", 0.05)

    passed = delta >= -threshold
    return {
        "baseline_faithfulness": baseline_faithfulness,
        "current_faithfulness": current_faithfulness,
        "delta": delta,
        "threshold": -threshold,
        "passed": passed,
        "verdict": (
            f"Faithfulness changed by {delta:+.3f} vs baseline "
            f"({'ACCEPTABLE' if passed else 'REGRESSION DETECTED'})"
        ),
    }


def run_eval(mode: str, baseline_path: str | None = None, version: str = "v1") -> dict:
    thresholds = load_thresholds()
    report: dict = {
        "eval_type": "prompt",
        "mode": mode,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    if mode == "stability":
        result = asyncio.run(run_stability_check(runs=20))
        passed = result["stable"]
        score = result["score"]

        print("\n── Prompt Stability Results ──────────────────────────────")
        threshold = thresholds["layer1_stability"]
        print(
            f"  layer1_stability: {score:.3f}  (threshold: {threshold:.2f})  "
            f"[{'PASS' if passed else 'FAIL'}]"
        )
        print("──────────────────────────────────────────────────────────")
        print(f"  Overall: {'PASS' if passed else 'FAIL'}")

        report.update(result)
        report["passed"] = passed

    elif mode == "regression":
        if not baseline_path:
            print("ERROR: --baseline required for regression mode")
            sys.exit(1)

        # Run a quick RAG eval to get current faithfulness score
        from harness.evals.rag.eval_retrieval import run_eval as run_rag_eval

        rag_report = run_rag_eval(smoke=True)
        comparison = compare_to_baseline(rag_report["scores"], Path(baseline_path))

        print("\n── Prompt Regression Results ─────────────────────────────")
        print(f"  {comparison['verdict']}")
        print(f"  {'PASS' if comparison['passed'] else 'FAIL'}")
        print("──────────────────────────────────────────────────────────")

        report.update(comparison)
        report["passed"] = comparison["passed"]

    elif mode == "save-baseline":
        from harness.evals.rag.eval_retrieval import run_eval as run_rag_eval

        rag_report = run_rag_eval(smoke=False)
        baseline = {
            "version": version,
            "timestamp": datetime.now(UTC).isoformat(),
            **rag_report["scores"],
        }
        baseline_out = REPO_ROOT / f"harness/reports/prompt_baseline_{version}.json"
        baseline_out.write_text(json.dumps(baseline, indent=2))
        print(f"Baseline saved to {baseline_out.relative_to(REPO_ROOT)}")
        report["saved_to"] = str(baseline_out)
        report["passed"] = True

    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_path = REPO_ROOT / f"harness/reports/prompt_{mode}_{ts}.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved: {report_path.relative_to(REPO_ROOT)}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=["stability", "regression", "save-baseline"], default="stability"
    )
    parser.add_argument("--baseline", help="Path to baseline JSON for regression mode")
    parser.add_argument("--version", default="v1", help="Version tag for save-baseline mode")
    args = parser.parse_args()

    report = run_eval(mode=args.mode, baseline_path=args.baseline, version=args.version)
    sys.exit(0 if report.get("passed", True) else 1)
