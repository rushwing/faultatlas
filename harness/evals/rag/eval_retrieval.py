"""
RAG Retrieval Quality Eval
Measures: context_precision, context_recall, faithfulness, answer_relevance
Framework: RAGAS (https://docs.ragas.io)

Usage:
    uv run python harness/evals/rag/eval_retrieval.py
    uv run python harness/evals/rag/eval_retrieval.py --smoke  # faster subset
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
from ragas import evaluate
from ragas.metrics import (
    context_precision,
    context_recall,
    faithfulness,
    answer_relevancy,
)
from datasets import Dataset

REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
RETRIEVER_BASE = os.getenv("RETRIEVER_BASE", "http://localhost:8001")
API_KEY = os.getenv("API_KEY", "changeme-local-dev")
GOLDEN_PATH = REPO_ROOT / "harness/datasets/golden/rag_golden.json"
THRESHOLDS_PATH = REPO_ROOT / "harness/thresholds.yaml"


async def retrieve_for_query(client: httpx.AsyncClient, query: str, top_k: int = 5) -> list[str]:
    """Call retriever service and return list of chunk contents."""
    resp = await client.post(
        f"{RETRIEVER_BASE}/search",
        json={"query": query, "top_k": top_k},
    )
    resp.raise_for_status()
    return [r["content"] for r in resp.json()["results"]]


async def diagnose_for_query(client: httpx.AsyncClient, query: str) -> str:
    """Call diagnosis endpoint and return the answer string."""
    resp = await client.post(
        f"{API_BASE}/diagnose",
        json={"query": query},
        headers={"X-API-Key": API_KEY},
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("summary", "")


async def build_ragas_dataset(golden: list[dict], smoke: bool = False) -> Dataset:
    """Build the Dataset expected by RAGAS from our golden set and live API calls."""
    cases = golden[:3] if smoke else golden

    questions, answers, contexts, ground_truths = [], [], [], []

    async with httpx.AsyncClient(timeout=30.0) as client:
        for case in cases:
            query = case["query"]
            chunks = await retrieve_for_query(client, query)
            answer = await diagnose_for_query(client, query)

            questions.append(query)
            contexts.append(chunks)
            answers.append(answer)
            # Ground truth: synthesized from expected keywords (good enough for eval)
            ground_truths.append(
                f"The incident involves {', '.join(case['expected_chunk_keywords'])}."
            )

    return Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "ground_truth": ground_truths,
    })


def load_thresholds() -> dict:
    import yaml
    with open(THRESHOLDS_PATH) as f:
        return yaml.safe_load(f)["rag"]


def run_eval(smoke: bool = False) -> dict:
    golden = json.loads(GOLDEN_PATH.read_text())

    print(f"Building RAGAS dataset from {len(golden)} golden queries{'  (smoke: 3 only)' if smoke else ''}...")
    dataset = asyncio.run(build_ragas_dataset(golden, smoke=smoke))

    print("Running RAGAS evaluation...")
    result = evaluate(
        dataset,
        metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
    )

    scores = {
        "context_precision": float(result["context_precision"]),
        "context_recall": float(result["context_recall"]),
        "faithfulness": float(result["faithfulness"]),
        "answer_relevance": float(result["answer_relevancy"]),
    }

    thresholds = load_thresholds()
    passed = True
    print("\n── RAG Eval Results ──────────────────────────────────────")
    for metric, score in scores.items():
        threshold = thresholds.get(metric, 0.0)
        status = "PASS" if score >= threshold else "FAIL"
        if status == "FAIL":
            passed = False
        print(f"  {metric:<28} {score:.3f}  (threshold: {threshold:.2f})  [{status}]")

    print("──────────────────────────────────────────────────────────")
    print(f"  Overall: {'PASS' if passed else 'FAIL'}")

    # Save report
    report = {
        "eval_type": "rag",
        "timestamp": datetime.now(UTC).isoformat(),
        "smoke": smoke,
        "scores": scores,
        "thresholds": thresholds,
        "passed": passed,
    }
    report_path = REPO_ROOT / f"harness/reports/rag_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\n  Report saved: {report_path.relative_to(REPO_ROOT)}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run subset (3 queries) for speed")
    args = parser.parse_args()

    report = run_eval(smoke=args.smoke)
    sys.exit(0 if report["passed"] else 1)
