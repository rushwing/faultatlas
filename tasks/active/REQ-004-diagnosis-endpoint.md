---
req_id: REQ-004
title: Structured diagnosis endpoint
status: draft
phase: phase-1
milestone: M1.3
priority: P0
depends_on: [REQ-001, REQ-002, REQ-003]
owner: danielwong
---

# User Story

As an on-call engineer, when I submit a natural language description of an active incident (e.g., "service startup failing, logs show repeated timeout and handshake errors"), I want the system to retrieve relevant runbook sections and historical cases, then return a structured diagnosis with suspected root causes, evidence citations, and recommended next actions, so I can reduce time-to-diagnose without manually correlating documents.

# Goal

Implement the end-to-end diagnosis pipeline: query → retrieve → prompt build → LLM → structured output. This is the primary user-facing capability of Phase 1 and the feature that makes the benchmark meaningful (REQ-005 depends on this producing consistent output).

The 3-layer prompt structure is **architecturally load-bearing** for prefix caching — it must be strictly followed.

# AI Behavior Definition

## Capability
- **Perceive:** incident description (natural language), session context (optional prior conversation in Phase 2)
- **Decide:** retrieve top-k evidence chunks (via retriever service), assemble the 3-layer prompt (system prefix → context scaffold → user query), call LLM, parse JSON response, store session
- **Generate:** `DiagnosisResponse` — structured JSON with summary, suspected causes, evidence citations, next actions, confidence, latency metrics
- **Interaction paradigm:** synchronous `POST /diagnose` — returns complete response when LLM finishes (streaming in Phase 2)

## Boundary
- Must NOT include variable content (timestamps, request IDs, user IDs) in **Layer 1 (system prefix)** — this would break prefix cache hit rate for every request
- Must NOT change chunk ordering in **Layer 2** between calls — ordering must be deterministic (score desc, chunk_id asc)
- Must NOT return a DiagnosisResponse with `evidence: []` when chunks were retrieved — if retrieval succeeded, evidence must cite the chunks used
- Must NOT hallucinate evidence: if a suspected cause is not supported by a retrieved chunk, the `evidence` array for that cause must be empty and `confidence` must be `"low"`
- Must NOT accept queries longer than 2000 tokens — return 400 with `detail: "query_too_long"`

## Fallback / Degradation
- Retriever service unavailable → return 503 with `detail: "retriever_unavailable"`
- LLM backend unavailable → return 503 with `detail: "llm_unavailable"`
- LLM returns non-parseable JSON → retry once with explicit JSON repair instruction; if still unparseable, return 500 with `detail: "llm_output_parse_error"` and raw LLM output in `debug_output`
- Empty knowledge base → proceed with empty context; set `confidence: "low"` and add `"note": "no_knowledge_base_content"` to response

# Deliverables

- [ ] `POST /diagnose` in `services/api/app/routers/query.py` (rename from current `query.py`)
- [ ] `services/api/app/agents/prompt_builder.py` — 3-layer prompt assembly
- [ ] `services/api/app/agents/orchestrator.py` — retrieve → build → call → parse pipeline
- [ ] `services/api/app/agents/response_parser.py` — JSON extraction + validation against DiagnosisResponse schema
- [ ] `DiagnosisResponse` Pydantic model in `services/api/app/schemas/diagnosis.py`
- [ ] MongoDB write: `agent_sessions` collection entry per call
- [ ] Unit tests: prompt builder (Layer 1 stability), response parser (valid/invalid JSON), confidence assignment
- [ ] Integration test: seed → diagnose → verify response schema

# API Contract

```
POST /diagnose
Headers:  X-API-Key: {key}
Body:     { query: string (max 2000 tokens), user_id?: string }
Response 200: {
  session_id: string,
  summary: string,
  suspected_causes: string[],
  evidence: [{ chunk_id, document_id, content, score }],
  next_actions: string[],
  confidence: "low" | "medium" | "high",
  latency_ms: int,
  tokens_used: int,
  prefix_cache_hint: "cold" | "shared" | "no_shared" | "unknown"
}
Response 400: { detail: "query_too_long" }
Response 503: { detail: "retriever_unavailable" | "llm_unavailable" }
Response 500: { detail: "llm_output_parse_error", debug_output?: string }
```

**Prompt structure (enforced in `prompt_builder.py`):**

```
[Layer 1 — SYSTEM, fixed ~800 tokens]
You are FaultAtlas, an expert AI assistant for log analysis and incident handling.
Output a JSON object matching exactly this schema: { summary, suspected_causes, evidence, next_actions, confidence }.
...role definition, citation rules, confidence rubric, safety disclaimers...

[Layer 2 — USER, semi-stable, ≤ 3000 tokens]
## Retrieved Evidence
{chunk_1_content}
---
{chunk_2_content}
...

[Layer 3 — USER continued, variable ≤ 200 tokens]
## Incident Description
{user_query}
```

# Acceptance Criteria

## Functional
1. Given 3 indexed documents and a query about OOM errors, response includes `summary`, at least 1 `suspected_cause`, at least 1 `evidence` entry matching an OOM chunk, and `confidence` in `["low","medium","high"]`
2. Given a query with no matching documents (empty KB), response has `confidence: "low"` and non-empty `summary` (LLM should say evidence is absent)
3. Given a malformed LLM JSON response (injected in test), the endpoint retries once and returns `parse_error` if retry also fails — does not hang or return 200 with garbage

## Performance / Quality
- End-to-end latency (OpenAI backend, warm cache): p95 < 8s
- End-to-end latency (SGLang, shared prefix, warm retrieval cache): target < 3s (this is the benchmark claim)
- `prefix_cache_hint` is populated for SGLang calls (may be `"unknown"` if SGLang header absent)

## Failure modes
- Layer 1 system prompt content is **identical** across 100 successive calls to the same endpoint — verified by hashing the system message string
- Variable user-specific content (user_id, timestamp) does NOT appear in the assembled prompt

# Eval Design

**Golden set:** `tests/integration/diagnosis_golden.json` — 3 queries with expected fields:
```json
[
  {
    "query": "Java OutOfMemoryError in payment-processor",
    "expected_confidence": ["medium", "high"],
    "expected_cause_keywords": ["heap", "memory"],
    "expected_evidence_min": 1
  }
]
```

**Measurement:**
```bash
uv run pytest tests/integration/test_diagnosis_quality.py -v
# Reports: schema validity, confidence match, evidence citation count
```

**Threshold:** all 3 golden queries return valid schema, at least 1 evidence per query, no parse errors

**Prompt stability check:**
```bash
uv run python tests/utils/check_prompt_stability.py
# Hashes Layer 1 content across 10 calls, asserts all hashes identical
```

# Model / Data Dependencies

- LLM: `Qwen2.5-7B-Instruct` (SGLang) or `gpt-4o-mini` (OpenAI) — prompt format tested against both
- Embedding: `text-embedding-3-small` — must match REQ-001 and REQ-002
- Layer 1 prompt: `services/api/app/agents/prompts.py::SYSTEM_PROMPT` — treat as a versioned artifact; any change must be tracked (add `PROMPT_VERSION` constant)
- Requires REQ-001 (at least 3 docs indexed) and REQ-002 (retriever running) before meaningful testing

# Out of Scope

- Streaming response / SSE (Phase 2 — REQ-007)
- Multi-turn conversation (Phase 2+)
- Tool calling / code execution (Phase 3+)
- Per-user knowledge base isolation (Phase 3)

# Notes for CodeX Review

- **Critical:** verify `prompt_builder.py` Layer 1 contains zero f-string interpolations or dynamic content
- **Critical:** verify `DiagnosisResponse` schema matches the contract exactly — `evidence` items must include `chunk_id`, not just `content`
- Check: is the JSON extraction in `response_parser.py` robust against markdown code fences (LLMs often wrap JSON in ```json...```)?
- Check: does the retry on parse failure send a different prompt (JSON repair instruction), or the exact same prompt? Same prompt will produce same bad output.
- Verify: is `PROMPT_VERSION` logged on every diagnosis call to `agent_sessions`?
