# FaultAtlas System Design

## Phase 1 Architecture — Single-Machine RAG Copilot

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              EXTERNAL CLIENTS                                   │
│                                                                                 │
│   curl / HTTP client / benchmark harness                                        │
└──────────────────────────────────┬──────────────────────────────────────────────┘
                                   │ HTTP
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         API SERVICE  :8000                                      │
│                                                                                 │
│  Routers                                                                        │
│  ├── POST /documents          → ingest.py       (sync HTTP pipeline)            │
│  ├── POST /diagnose           → diagnose.py     (RAG agent)                     │
│  ├── GET  /query              → query.py        (pass-through search)           │
│  ├── POST /benchmark/run      → benchmark.py    (TTFT benchmark)                │
│  ├── GET  /incidents          → incidents.py                                    │
│  └── GET  /health             → health.py                                       │
│                                                                                 │
│  Agent Orchestrator (orchestrator.py)                                           │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  1. retrieve_context() ──────────────────────────────────────────────►  │   │
│  │  2. build_diagnosis_prompt()                                             │   │
│  │     Layer 1: SYSTEM_PROMPT  (~800 tokens, fixed — cache anchor)         │   │
│  │     Layer 2: context scaffold (retrieved chunks, deterministic order)   │   │
│  │     Layer 3: user query (variable, appended last)                       │   │
│  │  3. llm_client.complete()                                                │   │
│  │  4. parse_diagnosis_output() → DiagnosisResponse                        │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  LLM Client (switchable via LLM_BACKEND env var)                                │
│  ├── LLM_BACKEND=sglang  → SGLang backend  (RadixAttention prefix cache)        │
│  └── LLM_BACKEND=openai  → OpenAI backend  (control / fallback)                 │
│                                                                                 │
│  Benchmark Runner (benchmark/runner.py)                                         │
│  ├── cold_start:       flush cache → repeated same-prefix queries               │
│  ├── shared_prefix:    5 variants sharing Layer 1+2 prefix                      │
│  └── no_shared_prefix: 5 unrelated queries (control group)                      │
└──────┬──────────────────────────────────────────────────────────────────────────┘
       │ HTTP  (retriever_url)
       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       RETRIEVER SERVICE  :8001  (internal)                      │
│                                                                                 │
│  POST /search                                                                   │
│  ├── redis_cache.py   → check RedisKeys.retriever:query_cache:{hash}  TTL 5m   │
│  ├── vector_search.py → cosine similarity over MongoDB chunks collection        │
│  │   ├── embed query via OpenAI embeddings API (or local fallback)              │
│  │   └── in-memory cosine scan (MVP; Atlas $vectorSearch in production)         │
│  └── context_builder.py → format top-k chunks for prompt Layer 2               │
└──────┬──────────────────────────────────────────────────────────────────────────┘
       │
       │  (ingestion path — sync HTTP in Phase 1)
       ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                       INGESTION SERVICE  (worker, no port)                      │
│                                                                                 │
│  Phase 1: stub worker (loops, no Kafka consumers active)                        │
│  Processors (called synchronously from API /documents route):                   │
│  ├── extractor.py   → parse raw document text                                   │
│  ├── chunker.py     → split into chunks                                         │
│  └── embedder.py    → OpenAI embeddings API → store vectors in MongoDB          │
│                                                                                 │
│  storage/                                                                       │
│  ├── mongo.py  → write to documents + chunks collections                        │
│  └── vector.py → write embeddings alongside chunk documents                     │
└─────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────┐
│                           INFRASTRUCTURE                                        │
│                                                                                 │
│  ┌──────────────────────┐   ┌──────────────────────┐                           │
│  │   MongoDB  :27017    │   │    Redis  :6379       │                           │
│  │                      │   │                       │                           │
│  │  Collections:        │   │  Key patterns:        │                           │
│  │  • documents         │   │  • api:session:{id}   │                           │
│  │  • chunks            │   │    TTL 30m            │                           │
│  │  • incidents         │   │  • retriever:query_   │                           │
│  │  • citations         │   │    cache:{hash} TTL5m │                           │
│  │  • benchmark_runs    │   │  • ingestion:status   │                           │
│  │  • agent_sessions    │   │    :{doc_id}  TTL 1h  │                           │
│  │  • audit_log         │   │  • benchmark:run:{id} │                           │
│  │                      │   │    TTL 1h             │                           │
│  │  Source of truth.    │   │                       │                           │
│  │  Redis never wins    │   │  Ephemeral cache only │                           │
│  │  on conflict.        │   │                       │                           │
│  └──────────────────────┘   └──────────────────────┘                           │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  SGLang Server  (GPU — RTX 4090)                                         │   │
│  │                                                                          │   │
│  │  Model: Qwen2.5-7B-Instruct (or Qwen3-8B)                               │   │
│  │  Feature: RadixAttention prefix caching                                  │   │
│  │                                                                          │   │
│  │  Benchmark target: shared-prefix TTFT ≤ 60% of cold-start TTFT          │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │  OpenAI API  (external)                                                  │   │
│  │  • Embeddings: text-embedding-* (ingestion + retrieval)                  │   │
│  │  • Chat completions: LLM_BACKEND=openai fallback                         │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────────┐
│                    STUBS — NOT ACTIVE IN PHASE 1                                │
│                                                                                 │
│  Kafka  :9092          shared/faultatlas/kafka/   — topics defined, not called  │
│  Kafka UI  :8080       provectuslabs/kafka-ui     — compose only                │
│  Prometheus/Grafana    infra/compose/obs overlay  — structured logs used instead│
│  Kubernetes            infra/k8s/                 — Phase 3 target              │
└─────────────────────────────────────────────────────────────────────────────────┘


## Request flow: POST /diagnose

  Client
    │  POST /diagnose  { query, session_id }
    ▼
  API :8000
    │  retrieve_context(query)
    ▼
  Retriever :8001
    │  check Redis query cache
    │  embed query (OpenAI)
    │  cosine scan MongoDB chunks
    │  return top-k chunks
    ▼
  API :8000
    │  build_diagnosis_prompt(query, chunks)
    │    [Layer1: fixed system prompt]
    │    [Layer2: chunk context scaffold]
    │    [Layer3: user query]
    │  llm_client.complete(messages)
    ▼
  SGLang / OpenAI
    │  RadixAttention hits prefix cache on Layer1+2
    │  returns content + ttft_ms + prefix_cache_hint
    ▼
  API :8000
    │  parse_diagnosis_output()
    │  write audit_log → MongoDB
    │  return DiagnosisResponse
    ▼
  Client
    { session_id, summary, suspected_causes, evidence,
      next_actions, confidence, latency_ms, tokens_used,
      prefix_cache_hint }


## Request flow: POST /benchmark/run

  Client
    │  POST /benchmark/run  { runs_per_condition? }
    ▼
  API :8000
    │  flush_cache() on SGLang
    │  ┌─ cold_start (N runs, same query, cache flushed each time)
    │  ├─ shared_prefix (N variant queries, same Layer1+2 prefix)
    │  └─ no_shared_prefix (N unrelated queries, control)
    │  summarize_condition() → p50/p95 TTFT, tokens/s
    │  build_hypothesis_result() → pass/fail vs 60% target
    │  insert benchmark_runs → MongoDB
    │  setex benchmark:run:{id} → Redis
    ▼
  Client
    { run_id, backend, model, hardware, conditions, hypothesis_result, raw_runs }


## Shared library  (shared/faultatlas/)

  faultatlas.mongo.client     — AsyncIOMotorClient, Collections enum
  faultatlas.redis.client     — Redis pool, RedisKeys patterns
  faultatlas.embeddings       — local embedding fallback (no OpenAI key)
  faultatlas.models.*         — Pydantic models: Document, Chunk, Incident
  faultatlas.events.*         — Event schemas: document, chunk, agent events
  faultatlas.kafka.*          — STUB: producer/consumer/topics (Phase 2+)
  faultatlas.ingestion        — shared ingestion helpers
```
