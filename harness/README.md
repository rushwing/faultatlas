# FaultAtlas Eval Harness

This directory contains AI quality evaluations — distinct from `tests/` which contains software correctness tests.

## The distinction

```
tests/          → Does the software behave correctly?
                  Pass/fail. Runs in CI on every PR.
                  Example: "POST /documents returns 409 on duplicate upload"

harness/evals/  → Does the AI output have sufficient quality?
                  Scored (0.0–1.0). Runs before releases and after prompt changes.
                  Example: "Are diagnosis outputs faithful to the retrieved evidence?"
```

## Four eval dimensions

```
harness/
  evals/
    model/    ← Which model is best for this task? (comparative)
    rag/      ← Is retrieval finding the right chunks? Is generation grounded?
    agent/    ← Is the diagnosis output structured, non-hallucinated, well-calibrated?
    prompt/   ← Is Layer 1 stable? Did a prompt change cause regression?
  datasets/
    golden/   ← Curated query→expected_output pairs (source of truth)
    fixtures/ ← Sample documents used as the knowledge base for evals
  reports/    ← Eval run outputs (gitignored except summaries)
```

## Running evals

```bash
# Full eval suite
make eval

# Individual dimensions
make eval-rag
make eval-agent
make eval-prompt
make eval-model     # requires GPU (compares multiple models)

# Quick smoke eval (fastest, runs subset)
make eval-smoke
```

## When to run

| Trigger | Eval to run |
|---|---|
| Before marking a REQ as `done` | `eval-rag` + `eval-agent` for that feature |
| Any change to `prompts.py` | `eval-prompt` (full suite) |
| Before a Phase milestone release | Full `eval` suite |
| Comparing Qwen2.5-7B vs Qwen3-8B | `eval-model` |
| After embedding model change | `eval-rag` (all retrieval metrics) |

## Thresholds

Defined in `harness/thresholds.yaml`. A PR that changes AI behavior is blocked if any threshold is not met.

See `docs/adr/ADR-004-eval-strategy.md` for the rationale behind each threshold.
