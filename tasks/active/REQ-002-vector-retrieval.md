---
req_id: REQ-002
title: Vector retrieval service
status: draft
phase: phase-1
milestone: M1.2
priority: P0
depends_on: [REQ-001]
owner: danielwong
---

# User Story

As the diagnosis agent, when given a natural language incident query, I want to retrieve the top-k most semantically relevant chunks from the knowledge base so that the prompt builder has grounded evidence to work with.

# Goal

Build the internal retrieval service (`services/retriever`) that the API calls during diagnosis. The retrieval quality directly determines whether the prefix cache benchmark is meaningful — if retrieved chunks are irrelevant, the diagnosis output is noise regardless of TTFT.

Phase 1 uses in-memory cosine similarity. This is intentionally simple: the bottleneck being measured is LLM serving latency, not retrieval latency.

# AI Behavior Definition

## Capability
- **Perceive:** natural language query string + `top_k` parameter
- **Decide:** embed the query using the same model as ingestion (`text-embedding-3-small`), then score all stored chunk embeddings by cosine similarity
- **Generate:** ranked list of `top_k` chunks with scores, ordered descending by score, then ascending by `chunk_id` for tie-breaking (deterministic ordering is required for prefix cache stability)
- **Interaction paradigm:** synchronous internal HTTP call from `services/api` — not a public endpoint

## Boundary
- Must NOT return chunks with `embedding` field absent — filter these out before scoring
- Must NOT change chunk ordering based on request time, random seed, or non-deterministic factors — prefix cache depends on identical Layer 2 content across similar queries
- Must NOT exceed the 3000-token context budget in `context_builder.py` — truncate by dropping lowest-scoring chunks, never by truncating chunk content mid-sentence
- Must NOT call the OpenAI embedding API more than once per query — cache the query embedding in the request scope (not Redis; query embeddings are not worth persisting)

## Fallback / Degradation
- Empty knowledge base (no chunks with embeddings) → return empty `results` list with HTTP 200, do not error
- Query embedding API failure → return HTTP 503 with `detail: "embedding_unavailable"` so the diagnosis endpoint can surface a meaningful error
- All chunks score below 0.3 → still return `top_k` results; do not apply a score threshold filter in Phase 1 (let the LLM handle low-quality context)

# Deliverables

- [ ] `POST /search` in `services/retriever/app/routers/search.py`
- [ ] `services/retriever/app/retrieval/vector_search.py` — cosine similarity scorer
- [ ] `services/retriever/app/retrieval/context_builder.py` — token budget trimmer
- [ ] `services/retriever/app/cache/redis_cache.py` — Redis result cache (5-min TTL keyed by `MD5(query + top_k)`)
- [ ] Unit tests: cosine similarity correctness, context_builder budget enforcement, cache hit/miss logic
- [ ] Integration test: seed 3 docs → query → verify top result is from the correct document

# API Contract

```
POST /search
Headers:  (internal only, no auth in Phase 1)
Body:     { query: string, top_k: int = 5 }
Response 200: {
  results: [
    { chunk_id, document_id, content, score: float }
  ]
}
Response 503: { detail: "embedding_unavailable" }
```

Redis cache key pattern: `retriever:query_cache:{MD5(query:top_k)}`  TTL: 300s

# Acceptance Criteria

## Functional
1. Given 3 indexed documents about OOM errors, network timeouts, and disk failures, when queried with "Java heap space error", then the top result's `document_id` matches the OOM document
2. Given the same query twice within 5 minutes, the second call is served from Redis cache (verified by checking Redis key exists)
3. Given an empty knowledge base, `POST /search` returns `{"results": []}` with HTTP 200

## Performance / Quality
- Retrieval latency (cache miss, 1000 chunks): p95 < 500ms on AutoDL CPU
- Retrieval latency (cache hit): p95 < 10ms
- Result ordering is deterministic: two identical queries always return chunks in identical order

## Failure modes
- When OpenAI embedding API returns 429, `/search` returns 503, not 500
- When `top_k=0`, return empty results list, not an error

# Eval Design

**Golden set:** 5 query → expected top document pairs, stored in `tests/integration/retrieval_golden.json`

```json
[
  { "query": "Java heap space OOM", "expected_document_keyword": "oom" },
  { "query": "TCP handshake timeout", "expected_document_keyword": "network" }
]
```

**Measurement:**
```bash
uv run pytest tests/integration/test_retrieval_quality.py -v
# Reports: precision@1 and precision@3 over golden set
```

**Threshold:** precision@1 ≥ 0.8 over 5 golden queries with the 3 seeded sample documents

# Model / Data Dependencies

- Embedding model: must match ingestion — `text-embedding-3-small`
- Requires REQ-001 complete: at least 3 documents indexed with embeddings
- Deterministic chunk ordering in responses is a **hard requirement** for REQ-005 (benchmark)

# Out of Scope

- BM25 keyword search (Phase 2 — REQ-008)
- Cross-encoder re-ranking (Phase 2 — REQ-008)
- MongoDB Atlas Vector Search (Phase 2 — replaces in-memory cosine)
- Per-user retrieval scope / access control (Phase 3)

# Notes for CodeX Review

- **Critical:** verify chunk ordering is fully deterministic (score desc, chunk_id asc for ties). Any non-determinism here will corrupt benchmark results in REQ-005
- Check: does `context_builder.py` drop complete chunks at the token budget boundary, or does it truncate the last chunk's content? (must drop, not truncate)
- Check: is the Redis cache keyed correctly? Two queries with different `top_k` must produce different cache keys
- Verify: does the golden set test actually fail if retrieval returns wrong results? (test should assert, not just print)
