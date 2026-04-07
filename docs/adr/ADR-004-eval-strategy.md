# ADR-004 — Evaluation Strategy

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-04-07 |
| **Deciders** | danielwong |

---

## Context

FaultAtlas has four distinct concerns that require measurement, often conflated in AI projects:

1. **Software correctness** — does the code do what it's supposed to do?
2. **Serving performance** — how fast is the LLM generating tokens?
3. **Retrieval quality** — are we finding the right chunks?
4. **Output quality** — is the AI diagnosis grounded, accurate, and calibrated?

Before this ADR, these concerns were mixed together: benchmark metrics lived in REQ files, there was no golden dataset, and the `tests/` directory was expected to cover both software correctness and AI quality. This conflation leads to a common failure mode: software tests all pass, but the AI outputs are hallucinated or poorly calibrated, and no one detects it until a user complains.

---

## Decision

Separate evaluation into four distinct dimensions, each with its own tooling, golden datasets, and threshold definitions.

### The four layers and what each measures

#### Layer 0 — Software correctness (`tests/`)
- **What:** Does the API return the right HTTP status codes? Does the chunker produce non-empty chunks? Does the idempotency key prevent duplicate uploads?
- **Tool:** pytest
- **When:** Every PR, in CI
- **Pass/fail:** Binary

#### Layer 1 — Serving performance (`scripts/run_benchmark.py`)
- **What:** What is the TTFT for cold vs. shared-prefix requests? Does SGLang RadixAttention produce the hypothesized ≤60% TTFT ratio?
- **Tool:** Custom benchmark pipeline (REQ-005), SGLang metrics
- **When:** Before each Phase milestone; after any SGLang config change
- **Pass/fail:** Hypothesis met (ratio ≤ 0.60) or not

#### Layer 2 — RAG quality (`harness/evals/rag/`)
- **What:** Is the retrieval finding relevant chunks? Is the generated answer grounded in the retrieved context?
- **Tool:** RAGAS (context_precision, context_recall, faithfulness, answer_relevancy)
- **Metrics and thresholds** (in `harness/thresholds.yaml`):
  - context_precision ≥ 0.70
  - context_recall ≥ 0.65
  - faithfulness ≥ 0.80
  - answer_relevance ≥ 0.75
- **When:** Before marking REQ-002 or REQ-004 done; after embedding model change; after retrieval logic change

#### Layer 3 — Agent quality (`harness/evals/agent/`)
- **What:** Is the diagnosis output structured correctly? Does it hallucinate causes not in the evidence? Is confidence calibrated correctly for low-evidence cases?
- **Tool:** DeepEval (HallucinationMetric, custom schema validator)
- **Metrics and thresholds:**
  - schema_validity = 1.00 (hard — 100% of responses must be parseable)
  - hallucination_score ≥ 0.85
  - confidence_calibration ≥ 0.70
  - evidence_citation_rate ≥ 0.90
- **When:** Before marking REQ-004 done; after any change to `orchestrator.py` or `response_parser.py`

#### Layer 4 — Prompt quality (`harness/evals/prompt/`)
- **What:** Is the Layer 1 system prompt stable (no variable content injected)? Did a prompt change cause regression in faithfulness?
- **Tool:** Custom stability checker + RAGAS regression comparison
- **Metrics and thresholds:**
  - layer1_stability = 1.00 (hard — all 20 calls must produce identical Layer 1 hash)
  - regression_threshold ≤ 0.05 faithfulness drop
- **When:** After ANY change to `prompts.py`; before any new prompt version is deployed

---

## Why RAGAS for RAG eval

RAGAS is chosen because:
1. It provides reference-free metrics — faithfulness and context precision do not require a gold-standard answer, only the retrieved context
2. It is directly aligned with the FaultAtlas use case (RAG over incident documents)
3. It is open-source and runs locally — no data leaves the machine (important for incident log content)
4. It uses an LLM as judge internally — configurable to use the local SGLang backend

RAGAS alternative considered: TruLens (Trulera). Rejected because it requires a hosted service and adds vendor lock-in.

## Why DeepEval for agent eval

DeepEval is chosen because:
1. It provides `HallucinationMetric` that scores against a provided context — directly tests whether diagnosis causes are grounded
2. `G-Eval` allows defining custom scoring criteria in natural language (e.g., "Does the confidence level match the strength of evidence?")
3. It integrates with pytest via `@pytest.mark.deepeval` — evals can run alongside tests during development

Alternative considered: direct LLM-as-judge with custom prompts. Rejected because maintaining custom judge prompts is maintenance overhead; DeepEval handles this.

## Why separate `harness/` from `tests/`

From mfg-copilot's architecture, adapted for FaultAtlas:

| | `tests/` | `harness/evals/` |
|---|---|---|
| Question answered | "Does the code do X?" | "Is the AI output good enough?" |
| Pass criterion | Binary (pass/fail) | Scored (≥ threshold) |
| Execution time | Fast (seconds) | Slow (minutes, LLM calls) |
| Run frequency | Every PR | Before releases, after AI changes |
| Flakiness | Low (deterministic) | Moderate (LLM calls have variance) |
| Data used | Mock/fixture | Live golden dataset |

If a test asserts software behavior, it belongs in `tests/`. If it judges AI output quality, it belongs in `harness/evals/`.

---

## Consequences

### Positive
- A prompt change that degrades faithfulness by 10% is caught by `make eval-prompt-regression` before it ships
- A retrieval change that improves precision@1 but degrades faithfulness is detected (they are separate metrics)
- Model comparison (`eval-model`) produces a structured report that can be cited in technical decisions

### Negative
- Eval runs are slow (5–15 minutes for full suite) — not suitable for CI on every PR
- RAGAS uses an LLM as judge internally, which means eval results have variance (run 3 times, get slightly different scores) — thresholds must account for this
- Golden datasets require maintenance: as the knowledge base grows, the expected top-document mappings in `rag_golden.json` may need updating

### Mitigation for LLM judge variance
- Run `make eval-rag` 3 times before accepting a result close to threshold
- Thresholds in `harness/thresholds.yaml` are set conservatively (5–10 points below observed scores) to absorb variance

---

## Threshold setting rationale

Thresholds are NOT set to 1.0 for most metrics because:
1. RAGAS metrics using LLM-as-judge have inherent variance (~±3–5 points)
2. The knowledge base in Phase 1 is small (3 sample documents) — recall will naturally be lower than production
3. Qwen2.5-7B has lower instruction-following reliability than GPT-4o — setting thresholds at GPT-4o performance levels would always fail

Thresholds should be **revisited after each Phase milestone** when the knowledge base and prompt have stabilized.
