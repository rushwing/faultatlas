---
req_id: REQ-008
title: Hybrid BM25 + vector retrieval
status: draft
phase: phase-2
milestone: M2.5
priority: P1
depends_on: [REQ-002]
owner: danielwong
---

# User Story

As an on-call engineer, when my incident involves specific error codes or exact log strings (e.g., "Error 0x8007054F"), I want keyword-based retrieval to surface exact matches that semantic similarity alone would miss, so that my diagnosis has higher evidence coverage for precise technical terms.

# Goal

Augment the Phase 1 vector-only retrieval with BM25 keyword search. Combine results using Reciprocal Rank Fusion (RRF). This addresses the known limitation of dense retrieval: out-of-distribution technical terms (error codes, service names, exact log patterns) often have poor vector similarity scores.

# AI Behavior Definition

## Capability
- **Perceive:** same query as REQ-002
- **Decide:** run vector search AND BM25 in parallel; merge results with RRF; apply context budget
- **Generate:** same `SearchResponse` schema as REQ-002 — hybrid is an implementation detail, not visible in the API contract

## Boundary
- Must NOT change the `SearchResponse` schema — REQ-004 and REQ-005 depend on it
- Must NOT let BM25 results dominate when the query is conceptual — RRF weight should be configurable (default: equal weight)

## Fallback / Degradation
- BM25 index unavailable → fall back to vector-only (Phase 1 behavior), log warning
- All BM25 scores are 0 → return vector results only

# Deliverables

- [ ] `services/retriever/app/retrieval/keyword_search.py` — BM25 over MongoDB text index
- [ ] `services/retriever/app/retrieval/rrf_merger.py` — Reciprocal Rank Fusion
- [ ] MongoDB text index on `chunks.content`
- [ ] `RETRIEVAL_MODE` env var: `vector` | `hybrid` (default: `hybrid` in Phase 2)
- [ ] Retrieval quality eval: compare hybrid vs. vector-only precision@3 on golden set

# Acceptance Criteria

1. Query for exact error code `"Error 0x8007054F"` returns the chunk containing that string in top-3 (fails with vector-only)
2. `precision@3` over 10-query golden set: hybrid ≥ vector-only + 5 percentage points
3. p95 retrieval latency with hybrid: < 800ms (vs. 500ms vector-only target from REQ-002)

# Eval Design

Extend `tests/integration/retrieval_golden.json` with 5 keyword-dependent queries.

```bash
uv run pytest tests/integration/test_retrieval_quality.py --mode hybrid -v
# Reports precision@1, precision@3 for both vector-only and hybrid
```

# Model / Data Dependencies

- MongoDB text index must be created at startup (migration script or `ensure_index` call)
- BM25 implementation: `rank_bm25` Python library, or MongoDB `$text` search

# Out of Scope

- Elasticsearch integration (Phase 3+)
- Cross-encoder neural re-ranking

# Notes for CodeX Review

- Verify RRF formula: `1 / (k + rank)` where `k=60` is standard — document the choice
- Check: does the fallback to vector-only work when `rank_bm25` raises an exception?
