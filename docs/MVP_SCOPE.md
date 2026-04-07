# FaultAtlas — MVP Scope Index

> **One-line definition:** A single-machine, low-latency, shared-prefix-friendly Incident RAG Copilot that validates SGLang prefix caching on a single RTX 4090.

**Last updated:** 2026-04-07
**Status:** Approved — Phase 1 active

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [MVP Hypothesis](#2-mvp-hypothesis)
3. [In-Scope Pipelines](#3-in-scope-pipelines)
4. [In-Scope Components](#4-in-scope-components)
5. [Out-of-Scope (Phase 1)](#5-out-of-scope-phase-1)
6. [Data Model Boundaries](#6-data-model-boundaries)
7. [API Surface](#7-api-surface)
8. [Prompt Architecture Constraints](#8-prompt-architecture-constraints)
9. [Success Criteria](#9-success-criteria)
10. [Explicitly Deferred Features](#10-explicitly-deferred-features)
11. [Document Index](#11-document-index)

---

## 1. Problem Statement

On-call engineers diagnosing incidents today face two bottlenecks:

1. **Knowledge fragmentation** — runbooks, past cases, and log patterns live in different places and require manual correlation.
2. **LLM latency** — RAG-based copilots are useful but too slow to feel interactive when the model is run locally under constrained hardware.

This MVP targets both in the smallest possible footprint: build a working RAG copilot *and* demonstrate that the serving architecture (SGLang + prefix caching) meaningfully solves the latency problem.

---

## 2. MVP Hypothesis

> If we structure the RAG prompt with a large, stable system prefix and use SGLang's RadixAttention-based KV cache, then repeated queries against the same knowledge base will show measurably lower TTFT than cold-start requests — on a single RTX 4090, using a Qwen2.5-7B or Qwen3-8B model.

**This hypothesis is falsifiable.** The benchmark pipeline is not optional — it is the core deliverable.

---

## 3. In-Scope Pipelines

### Pipeline 1 — Ingest

```
Upload file (runbook / incident case / log sample)
  → extract text (PDF → text, plain text passthrough)
  → chunk (fixed-size with overlap)
  → embed (OpenAI API or local embedding model)
  → store chunks + metadata in MongoDB
  → update document status in Redis
```

Goal: build the knowledge base. **Not** a real-time streaming pipeline.
Trigger: HTTP file upload. Synchronous in Phase 1.

### Pipeline 2 — Retrieve

```
Incident query (natural language)
  → embed query
  → cosine similarity against stored chunk vectors (MongoDB MVP)
  → return top-k chunks with scores
  → cache result in Redis (5 min TTL, keyed by query hash)
```

Goal: fast, deterministic retrieval. No re-ranking, no multi-hop. Constrained intentionally.

### Pipeline 3 — Diagnose

```
Retrieved chunks
  → Prompt Builder (3-layer fixed template)
  → SGLang / OpenAI-compatible POST /v1/chat/completions
  → parse structured JSON response
  → return DiagnosisResponse with evidence citations
```

Goal: structured output, every time. Output schema is fixed. No free-form generation.

**Output schema:**
```json
{
  "summary": "string",
  "suspected_causes": ["string"],
  "evidence": [{ "chunk_id": "string", "content": "string", "score": 0.0 }],
  "next_actions": ["string"],
  "confidence": "low | medium | high",
  "latency_ms": 0,
  "tokens_used": 0,
  "prefix_cache_hint": "cold | shared | no_shared"
}
```

### Pipeline 4 — Benchmark

```
Benchmark trigger (HTTP POST /benchmark/run)
  → run 3 request types:
      (a) cold_start       — first request, empty KV cache
      (b) shared_prefix    — same system + context prefix, different user query
      (c) no_shared_prefix — completely different prompt structure
  → capture per-request: TTFT, total latency, tokens/s
  → store BenchmarkRun document in MongoDB
  → return comparison report
```

Goal: produce a concrete, shareable number that proves the prefix cache advantage.

---

## 4. In-Scope Components

### A. Data layer

**MongoDB collections:**

| Collection | Purpose |
|---|---|
| `documents` | Source file metadata, ingestion status |
| `chunks` | Text chunks with embeddings |
| `incidents` | Incident records with timeline |
| `citations` | Evidence references per diagnosis session |
| `benchmark_runs` | Benchmark results with per-request metrics |
| `agent_sessions` | Diagnosis session history |
| `audit_log` | Immutable event trail |

**Redis key patterns:**

| Pattern | Purpose | TTL |
|---|---|---|
| `api:session:{session_id}` | Diagnosis session state | 30 min |
| `retriever:query_cache:{query_hash}` | Retrieval result cache | 5 min |
| `ingestion:status:{document_id}` | Document processing status | 1 hr |
| `ingestion:idempotency:{doc_hash}` | Prevent duplicate uploads | 24 hr |
| `benchmark:run:{run_id}` | Active benchmark task state | 1 hr |

### B. Model layer

- **Serving:** SGLang with OpenAI-compatible HTTP server (`/v1/chat/completions`)
- **Primary model:** `Qwen/Qwen2.5-7B-Instruct` or `Qwen/QwQ-32B` (if VRAM allows)
- **Fallback / API mode:** OpenAI API (switchable via `LLM_BACKEND` env var)
- **Embedding:** OpenAI `text-embedding-3-small` (external API, Phase 1)

### C. Application layer

| Service | Responsibility |
|---|---|
| `services/api` | HTTP gateway, diagnosis endpoint, benchmark endpoint, incident CRUD |
| `services/retriever` | Internal vector search, context assembly, Redis cache |
| `services/ingestion` | Document processing worker (sync HTTP handler in Phase 1, Kafka consumer in Phase 2) |
| `shared/` | Pydantic models, event schemas, Kafka/Mongo/Redis client wrappers |

### D. Infrastructure layer

| Layer | Phase 1 | Phase 2+ |
|---|---|---|
| Runtime | Docker Compose (single machine) | Docker Compose + optional K8S |
| Event bus | None (direct HTTP) | Kafka |
| K8S manifests | Stub only | Active |
| Observability | Structured JSON logs only | Prometheus + Grafana + Loki |

---

## 5. Out-of-Scope (Phase 1)

The following are explicitly **not** part of MVP Phase 1. They are documented here to prevent scope creep.

| Feature | Reason excluded |
|---|---|
| Multi-agent orchestration | Does not improve prefix cache hit rate; adds complexity |
| Automatic planner / tool registry | Same reason; free-form tool descriptions fragment the prefix |
| Kafka real-time log streaming | Phase 2; ingestion is synchronous upload in Phase 1 |
| Web frontend / dashboard | Swagger UI is sufficient for demo; frontend delays core validation |
| User auth / RBAC | Not needed for single-engineer MVP validation |
| Multi-tenancy | Out of scope until commercial phase |
| Full K8S autoscaling | Phase 3 |
| Production observability (OTel tracing, alerting) | Phase 2 partial, Phase 3 full |
| Re-ranking / hybrid BM25 | Phase 2; adds retrieval quality but not needed for perf proof |
| Streaming SSE responses | Phase 2; adds demo value but not needed for benchmark |
| Feedback loop / fine-tuning dataset | Phase 3 / commercial |

---

## 6. Data Model Boundaries

### What lives in MongoDB
- All persistent state: documents, chunks, embeddings, incidents, sessions, benchmark runs, audit log
- Embeddings stored inline on chunk documents (MVP — no separate vector DB)

### What lives in Redis
- All ephemeral state: session context, retrieval cache, processing status flags, idempotency keys, benchmark task state
- Nothing in Redis is source of truth — MongoDB is authoritative

### What is stateless
- All three application services (`api`, `retriever`, `ingestion`) carry zero in-process state
- Any horizontal scaling of these services requires only MongoDB + Redis to be available

---

## 7. API Surface

### Public endpoints (via `services/api`, port 8000)

```
POST   /documents                    Upload document for ingestion
GET    /documents/{id}/status        Check processing status

POST   /diagnose                     Submit incident query, get structured diagnosis
GET    /diagnose/{session_id}        Retrieve diagnosis session

GET    /incidents                    List incidents
POST   /incidents                    Create incident
GET    /incidents/{id}               Get incident detail

POST   /benchmark/run                Trigger benchmark suite
GET    /benchmark/latest             Get latest benchmark report
GET    /benchmark/{run_id}           Get specific run

GET    /health                       Liveness
GET    /ready                        Readiness (checks Mongo + Redis)
```

### Internal endpoints (via `services/retriever`, port 8001)

```
POST   /search                       Vector search, returns top-k chunks
GET    /health
```

---

## 8. Prompt Architecture Constraints

These constraints are **load-bearing for the benchmark**. Changing them will degrade prefix cache hit rate and invalidate the performance hypothesis.

### The three-layer rule

Every request to the LLM **must** use this structure, in this order:

```
Layer 1 — System prefix      (fixed per prompt version, ~800 tokens)
Layer 2 — Context scaffold   (retrieved evidence, semi-stable)
Layer 3 — User query         (variable, appended last, ~50–200 tokens)
```

### Constraints on Layer 1
- Contains: role definition, output JSON schema, citation rules, confidence rubric, safety disclaimers
- **Must not change** between requests of the same prompt version
- Prompt versioning is tracked — changing Layer 1 creates a new version and resets the cache

### Constraints on Layer 2
- Retrieved chunks are inserted in **deterministic order** (descending score, then ascending chunk_id for ties)
- Maximum token budget: 3000 tokens
- No free-form additions (no dynamic tool descriptions, no per-user customization)

### Constraints on Layer 3
- Only the raw incident description / alert text
- No injected metadata that varies per session (no timestamps, no user IDs, no request IDs)

### Why this matters
SGLang's RadixAttention caches the KV state of matched prefix tokens. Two requests share a prefix if and only if their token sequences are identical up to some prefix length. Violating any of the above constraints (e.g., injecting a timestamp into Layer 1, shuffling chunk order in Layer 2) will break prefix identity and produce cache misses.

---

## 9. Success Criteria

### Functional success

| Criterion | Measurement |
|---|---|
| Diagnosis pipeline end-to-end | Upload 3 test docs → query → receive valid JSON DiagnosisResponse |
| Evidence citation | Response includes at least 1 evidence entry with chunk_id and content |
| Stability | 10 consecutive queries against same knowledge base all return valid responses |
| Backend switchability | Setting `LLM_BACKEND=openai` uses OpenAI API without code changes |

### Performance success (primary)

| Criterion | Target |
|---|---|
| Shared-prefix TTFT vs. cold-start | Shared-prefix TTFT ≤ 60% of cold-start TTFT (on same model/hardware) |
| Shared-prefix advantage vs. no-shared-prefix | Shared-prefix TTFT measurably lower; documented in benchmark report |
| Context length stability | Handles 8k–12k token contexts without OOM on RTX 4090 |
| Sustained throughput | 10 concurrent requests without service degradation |
| Benchmark reproducibility | Two successive `POST /benchmark/run` calls produce results within 15% of each other |

---

## 10. Explicitly Deferred Features

The following features have been considered and deliberately deferred. They should not be added to Phase 1 without updating this document.

| Feature | Target phase | Trigger condition |
|---|---|---|
| Kafka async ingestion | Phase 2 | When upload latency becomes a demo bottleneck |
| Async benchmark tasks | Phase 2 | When benchmark takes > 30s and blocks the HTTP response |
| Streaming LLM responses (SSE) | Phase 2 | When demo UX needs real-time feel |
| Hybrid BM25 + vector retrieval | Phase 2 | When retrieval quality is the bottleneck |
| Re-ranking | Phase 2 | Same trigger as hybrid retrieval |
| Prometheus metrics + Grafana | Phase 2 | When benchmark numbers need time-series visualization |
| K8S Helm chart | Phase 3 | When moving from AutoDL to cloud deployment |
| React frontend | Phase 3 or commercial | When doing an external demo or customer pilot |
| Multi-tenancy / auth | Commercial Phase 1 | When onboarding first external user |

---

## 11. Document Index

| Document | Purpose |
|---|---|
| `README.md` | Quick start, architecture overview, configuration reference |
| `docs/MVP_SCOPE.md` | **This document** — authoritative scope definition |
| `docs/MVP_DEV_PHASES.md` | Phase breakdown with milestones and exit criteria |
| `docs/adr/ADR-001-mvp-scope-definition.md` | Why this scope was chosen over alternatives |
| `docs/adr/ADR-002-technology-selection.md` | Tech stack decisions and trade-offs |
| `docs/adr/ADR-003-commercial-evolution.md` | Path from MVP to commercial product |
