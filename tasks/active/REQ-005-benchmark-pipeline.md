---
req_id: REQ-005
title: Prefix cache benchmark pipeline
status: draft
phase: phase-1
milestone: M1.4
priority: P0
depends_on: [REQ-003, REQ-004]
owner: danielwong
---

# User Story

As a performance engineer validating the SGLang deployment, I want to run a structured benchmark that compares TTFT and throughput across three request types (cold start, shared-prefix repeated, no-shared-prefix), so I can produce a concrete, shareable number that proves or disproves the prefix caching hypothesis on this hardware.

# Goal

This is the **primary deliverable of Phase 1**. The benchmark must produce a result that directly tests the core hypothesis from ADR-001:

> Shared-prefix repeated requests against SGLang will show ≤ 60% of the TTFT of cold-start requests, on a single RTX 4090 with Qwen2.5-7B-Instruct.

The benchmark is not a load test — it is a controlled experiment with three specific conditions. Each condition must be run in isolation to avoid KV cache contamination.

# AI Behavior Definition

## Capability
- **Perceive:** benchmark configuration (number of runs per condition, query set, model backend)
- **Decide:** orchestrate three request types with controlled inter-request state; capture per-request TTFT, total latency, tokens/s; compute aggregate statistics (mean, p50, p95, p99)
- **Generate:** `BenchmarkRun` document stored in MongoDB + summary report returned via HTTP
- **Interaction paradigm:** triggered via `POST /benchmark/run`, result stored and queryable via `GET /benchmark/latest`

## The three request types

**Type A — cold_start:**
- Purpose: establish baseline TTFT with empty KV cache
- Method: restart SGLang server (or call `/flush_cache` if available) between calls
- What varies: nothing — same prompt, same query, cold cache each time
- N = 5 runs, report mean + stdev

**Type B — shared_prefix:**
- Purpose: measure prefix cache benefit on repeated RAG queries
- Method: same Layer 1 (system) + same Layer 2 (context chunks) + 5 different Layer 3 (user queries)
- Condition: no cache flush between calls — KV cache accumulates
- What varies: only Layer 3 (user query, ~50–200 tokens)
- N = 5 runs (one per query variant), report mean + stdev

**Type C — no_shared_prefix:**
- Purpose: control condition — different prompt structure each call, no prefix overlap
- Method: 5 calls where Layer 1 AND Layer 2 are different each time (different context chunks)
- What varies: Layer 1 + Layer 2 content (simulates a poorly-structured RAG prompt)
- N = 5 runs, report mean + stdev

## Boundary
- Must NOT run Type B before Type A (cache must be cold for Type A baseline)
- Must NOT mix OpenAI and SGLang runs in the same benchmark report — backends are not comparable
- Must NOT count retrieval time or embedding time in TTFT — TTFT is measured from the moment the HTTP request to the LLM is sent to the moment the first byte of response is received
- Must NOT fail silently — if any individual run errors, mark that run as failed and continue; report error count in summary

## Fallback / Degradation
- SGLang `/flush_cache` endpoint not available → warm the model with a dummy request and note in report that cold_start condition may be inaccurate
- SGLang server OOM during benchmark → halt benchmark, save partial results, return 500 with partial report

# Deliverables

- [ ] `POST /benchmark/run` in `services/api/app/routers/benchmark.py`
- [ ] `GET /benchmark/latest` and `GET /benchmark/{run_id}`
- [ ] `services/api/app/benchmark/runner.py` — orchestrates A/B/C conditions
- [ ] `services/api/app/benchmark/metrics.py` — TTFT capture, statistics computation
- [ ] `services/api/app/benchmark/report.py` — formats BenchmarkRun into human-readable summary
- [ ] MongoDB: `benchmark_runs` collection schema
- [ ] Redis: `benchmark:run:{run_id}` for in-progress state (TTL 1h)
- [ ] `scripts/run_benchmark.py` — CLI wrapper that calls the API and pretty-prints the report
- [ ] Unit tests: metrics computation, report formatting, condition isolation logic

# API Contract

```
POST /benchmark/run
Headers:  X-API-Key: {key}
Body:     { backend?: "sglang"|"openai", runs_per_condition?: int = 5 }
Response 200: {
  run_id: string,
  backend: string,
  model: string,
  hardware: string,
  conditions: {
    cold_start:        { runs, mean_ttft_ms, p95_ttft_ms, mean_tokens_per_sec, error_count },
    shared_prefix:     { runs, mean_ttft_ms, p95_ttft_ms, mean_tokens_per_sec, error_count },
    no_shared_prefix:  { runs, mean_ttft_ms, p95_ttft_ms, mean_tokens_per_sec, error_count }
  },
  hypothesis_result: {
    shared_vs_cold_ratio: float,   # shared_prefix.mean_ttft / cold_start.mean_ttft
    hypothesis_met: bool,          # ratio <= 0.60
    verdict: string                # human-readable explanation
  },
  created_at: ISO8601
}

GET /benchmark/latest
Response 200: same as above (most recent completed run)

GET /benchmark/{run_id}
Response 200: same | 404 if not found
```

MongoDB `benchmark_runs` document:
```json
{
  "_id": "uuid",
  "backend": "sglang",
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "hardware": "RTX 4090 24GB",
  "conditions": { ... },
  "hypothesis_result": { ... },
  "raw_runs": [{ "condition", "run_index", "ttft_ms", "total_ms", "tokens_per_sec", "error"? }],
  "created_at": "ISO8601"
}
```

# Acceptance Criteria

## Functional
1. `POST /benchmark/run` with `backend=sglang` completes and returns a valid report with all 3 conditions populated
2. `hypothesis_result.shared_vs_cold_ratio` is a float between 0.0 and 2.0 (sanity check)
3. `GET /benchmark/latest` returns the most recently completed run
4. If any individual LLM call errors, the benchmark continues and reports `error_count > 0` — it does not abort

## Performance / Quality (the actual hypothesis)
- `hypothesis_result.shared_vs_cold_ratio ≤ 0.60` on RTX 4090 with Qwen2.5-7B-Instruct
- `shared_prefix.mean_ttft_ms < no_shared_prefix.mean_ttft_ms` (prefix cache is better than no prefix)
- `cold_start.p95_ttft_ms` is reproducible within ±15% across two successive benchmark runs

## Failure modes
- When `backend=openai` is specified, the benchmark runs but `prefix_cache_hint` is `"unknown"` for all runs — the report notes this limitation
- When SGLang is down, `POST /benchmark/run` returns 503 immediately — does not start a partial run

# Eval Design

The benchmark IS the eval. The measurement script:

```bash
# Run benchmark and check hypothesis
uv run python scripts/run_benchmark.py --backend sglang --runs 5

# Expected output:
# cold_start mean TTFT:       XXX ms
# shared_prefix mean TTFT:    YYY ms  (target: ≤ 60% of cold_start)
# no_shared_prefix mean TTFT: ZZZ ms
# hypothesis_met: TRUE/FALSE
```

Save the output to `docs/benchmark_phase1.md` — this is a required Phase 1 deliverable.

**Reproducibility check:**
```bash
# Run twice, compare ratios
uv run python scripts/run_benchmark.py --backend sglang > run1.json
uv run python scripts/run_benchmark.py --backend sglang > run2.json
python scripts/compare_benchmarks.py run1.json run2.json
# Assert: shared_vs_cold_ratio within ±15% between runs
```

# Model / Data Dependencies

- Requires SGLang running with Qwen2.5-7B-Instruct on RTX 4090
- Requires REQ-004: diagnosis endpoint producing consistent 3-layer prompts
- Requires REQ-001: at least 3 documents indexed (for Type B shared context)
- **Prompt Layer 1 must be identical across all 15 runs** — any drift invalidates the experiment
- SGLang version: ≥ 0.3 recommended for `x-prefix-cache-hit` header support

# Out of Scope

- Async benchmark execution (Phase 2 — REQ-010)
- Multi-GPU throughput benchmarks (Phase 3 — REQ-013)
- vLLM comparison benchmark (Phase 2 optional)
- Load testing (concurrent users) — this is a latency experiment, not a throughput test

# Notes for CodeX Review

- **Critical:** verify Type A (cold_start) genuinely flushes the KV cache before each run — if SGLang `/flush_cache` is used, confirm the endpoint exists in the target SGLang version; if not, document the limitation
- **Critical:** verify TTFT is measured from HTTP request send to first response byte — NOT from function call start (which includes Python overhead)
- Check: is `raw_runs` stored in MongoDB? The aggregate statistics alone are not sufficient — raw data enables post-hoc analysis
- Check: does `hypothesis_result.verdict` produce a human-readable string that can be directly copy-pasted into a report? (e.g., "Shared-prefix TTFT (312ms) is 48% of cold-start TTFT (648ms). Hypothesis MET.")
- Verify: are Type A, B, C run in strict sequence (A → B → C), never in parallel?
