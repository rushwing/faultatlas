"""
Agent / Diagnosis Quality Eval
Measures: schema_validity, hallucination_score, confidence_calibration, evidence_citation_rate
Framework: DeepEval (https://docs.confident-ai.com)

Usage:
    uv run python harness/evals/agent/eval_diagnosis.py
    uv run python harness/evals/agent/eval_diagnosis.py --smoke
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, UTC

import httpx
from deepeval import evaluate as deepeval_evaluate
from deepeval.metrics import (
    HallucinationMetric,
    FaithfulnessMetric,
    AnswerRelevancyMetric,
)
from deepeval.test_case import LLMTestCase

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
API_KEY = os.getenv("API_KEY", "changeme-local-dev")
GOLDEN_PATH = REPO_ROOT / "harness/datasets/golden/agent_golden.json"
THRESHOLDS_PATH = REPO_ROOT / "harness/thresholds.yaml"


def load_thresholds() -> dict:
    import yaml
    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)["agent"]


def validate_schema(response: dict) -> tuple[bool, str]:
    """Validate DiagnosisResponse schema completeness."""
    required = ["session_id", "summary", "suspected_causes", "evidence",
                "next_actions", "confidence", "latency_ms", "tokens_used"]
    missing = [f for f in required if f not in response]
    if missing:
        return False, f"Missing fields: {missing}"
    if response["confidence"] not in ("low", "medium", "high"):
        return False, f"Invalid confidence value: {response['confidence']}"
    if not isinstance(response["suspected_causes"], list):
        return False, "suspected_causes must be a list"
    if not isinstance(response["evidence"], list):
        return False, "evidence must be a list"
    return True, "ok"


async def run_case(client: httpx.AsyncClient, case: dict) -> dict:
    """Run a single golden case against the diagnosis API."""
    try:
        resp = await client.post(
            f"{API_BASE}/diagnose",
            json={"query": case["query"]},
            headers={"X-API-Key": API_KEY},
            timeout=30.0,
        )
        resp.raise_for_status()
        response = resp.json()
        schema_valid, schema_msg = validate_schema(response)

        # Build retrieval context for hallucination check
        context = [e["content"] for e in response.get("evidence", [])]

        return {
            "id": case["id"],
            "query": case["query"],
            "response": response,
            "schema_valid": schema_valid,
            "schema_msg": schema_msg,
            "has_evidence": len(response.get("evidence", [])) > 0,
            "confidence": response.get("confidence"),
            "summary": response.get("summary", ""),
            "context": context,
            "error": None,
        }
    except Exception as e:
        return {
            "id": case["id"],
            "query": case["query"],
            "response": None,
            "schema_valid": False,
            "schema_msg": str(e),
            "has_evidence": False,
            "confidence": None,
            "summary": "",
            "context": [],
            "error": str(e),
        }


def build_deepeval_cases(results: list[dict]) -> list[LLMTestCase]:
    """Convert our results to DeepEval test cases for hallucination + faithfulness scoring."""
    cases = []
    for r in results:
        if r["error"] or not r["schema_valid"]:
            continue
        cases.append(LLMTestCase(
            input=r["query"],
            actual_output=r["summary"],
            context=r["context"] if r["context"] else ["No evidence retrieved"],
            expected_output=None,  # we use context-based metrics, not exact match
        ))
    return cases


def run_eval(smoke: bool = False) -> dict:
    golden = json.loads(GOLDEN_PATH.read_text())
    cases = golden[:2] if smoke else golden
    thresholds = load_thresholds()

    print(f"Running {len(cases)} diagnosis cases{'  (smoke)' if smoke else ''}...")
    results = asyncio.run(
        asyncio.gather(*[
            _run_all(cases)
        ])
    )[0]

    # Schema validity
    schema_valid_count = sum(1 for r in results if r["schema_valid"])
    schema_validity = schema_valid_count / len(results)

    # Evidence citation rate
    evidence_rate = sum(1 for r in results if r["has_evidence"]) / len(results)

    # Confidence calibration: empty-KB case should return "low"
    empty_kb_cases = [c for c in golden if not c.get("fixture_documents")]
    empty_kb_results = [r for r in results if r["id"] in {c["id"] for c in empty_kb_cases}]
    calibration_ok = all(r["confidence"] == "low" for r in empty_kb_results if r["confidence"])
    confidence_calibration = 1.0 if calibration_ok else 0.0

    # DeepEval hallucination scoring
    deepeval_cases = build_deepeval_cases(results)
    hallucination_scores = []
    if deepeval_cases:
        hal_metric = HallucinationMetric(threshold=thresholds["hallucination_score"])
        for tc in deepeval_cases:
            hal_metric.measure(tc)
            hallucination_scores.append(hal_metric.score)
    hallucination_score = sum(hallucination_scores) / len(hallucination_scores) if hallucination_scores else 0.0

    scores = {
        "schema_validity": schema_validity,
        "hallucination_score": hallucination_score,
        "confidence_calibration": confidence_calibration,
        "evidence_citation_rate": evidence_rate,
    }

    passed = True
    print("\n── Agent Eval Results ────────────────────────────────────")
    for metric, score in scores.items():
        threshold = thresholds.get(metric, 0.0)
        status = "PASS" if score >= threshold else "FAIL"
        if status == "FAIL":
            passed = False
        print(f"  {metric:<28} {score:.3f}  (threshold: {threshold:.2f})  [{status}]")

    print("──────────────────────────────────────────────────────────")
    print(f"  Overall: {'PASS' if passed else 'FAIL'}")

    # Print failures
    for r in results:
        if not r["schema_valid"]:
            print(f"\n  [SCHEMA FAIL] {r['id']}: {r['schema_msg']}")
        if r["error"]:
            print(f"\n  [ERROR] {r['id']}: {r['error']}")

    report = {
        "eval_type": "agent",
        "timestamp": datetime.now(UTC).isoformat(),
        "smoke": smoke,
        "scores": scores,
        "thresholds": thresholds,
        "passed": passed,
        "case_results": [
            {"id": r["id"], "schema_valid": r["schema_valid"],
             "has_evidence": r["has_evidence"], "confidence": r["confidence"]}
            for r in results
        ],
    }
    report_path = REPO_ROOT / f"harness/reports/agent_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved: {report_path.relative_to(REPO_ROOT)}")

    return report


async def _run_all(cases: list[dict]) -> list[dict]:
    async with httpx.AsyncClient() as client:
        return await asyncio.gather(*[run_case(client, c) for c in cases])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()

    report = run_eval(smoke=args.smoke)
    sys.exit(0 if report["passed"] else 1)
