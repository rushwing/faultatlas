# FaultAtlas — MVP Development Phases

> This document defines the three development phases, their scope, milestones, exit criteria, and the sequencing rationale. It is the authoritative reference for "what are we building right now and what comes next."

**Last updated:** 2026-04-07

---

## Phase Overview

| Phase | Name | Focus | Hardware target | Status |
|---|---|---|---|---|
| **Phase 1** | Inference-first MVP | Core 4 pipelines + benchmark | AutoDL RTX 4090, single machine | **Active** |
| **Phase 2** | Service hardening | Async pipeline, metrics, streaming | AutoDL or equivalent | Planned |
| **Phase 3** | Cloud-native packaging | K8S, Helm, production readiness | Cloud GPU instance | Future |

The phases are deliberately **thin verticals**, not horizontal layers. Each phase produces something runnable and demonstrable end-to-end.

---

## Phase 1 — Inference-first MVP

### Objective

Prove that a Qwen2.5-7B-Instruct (or Qwen3-8B) model served by SGLang on a single RTX 4090, with a fixed 3-layer prompt structure, delivers measurably lower TTFT on shared-prefix repeated requests compared to cold-start — while providing a working structured diagnostic output.

This is a **performance proof-of-concept wrapped in a minimal application**.

### Scope

**Services active:**
- `services/api` — all 4 core pipelines (ingest, retrieve, diagnose, benchmark)
- `services/retriever` — vector search + Redis cache
- `services/ingestion` — synchronous HTTP handler (no Kafka yet)
- `shared/` — full models, Kafka stubs, Mongo/Redis clients

**Infrastructure active:**
- Docker Compose: MongoDB, Redis, SGLang container
- Kafka: defined in compose file but **not used** in Phase 1 application code

**Not active:**
- Kafka consumers/producers in application code
- K8S manifests (files exist as stubs)
- Prometheus/Grafana stack
- Frontend

### Milestones

#### M1.1 — Knowledge base works (Week 1)

- [ ] `POST /documents` accepts PDF and plain text, stores in MongoDB
- [ ] Chunking pipeline produces chunks with correct token counts
- [ ] OpenAI embedding API integration working
- [ ] Document status tracked in Redis
- [ ] `GET /documents/{id}/status` returns current stage
- [ ] Unit tests: chunker, extractor, context_builder

**Exit check:** `uv run python scripts/seed_data.py` completes without error; 3 sample documents indexed.

#### M1.2 — Retrieval works (Week 1–2)

- [ ] `POST /search` (retriever service) returns top-k chunks with cosine scores
- [ ] Redis retrieval cache working (second call for same query is a cache hit)
- [ ] Context builder respects token budget
- [ ] Prompt builder generates correct 3-layer prompt (Layer 1 stable across calls)

**Exit check:** Query against seeded knowledge base returns ≥ 1 relevant chunk with score > 0.6.

#### M1.3 — SGLang integration works (Week 2)

- [ ] SGLang server starts with Qwen2.5-7B-Instruct, `/v1/chat/completions` reachable
- [ ] `LLM_BACKEND=sglang` path calls SGLang server correctly
- [ ] `LLM_BACKEND=openai` path calls OpenAI API (fallback verified)
- [ ] DiagnosisResponse JSON schema is always parseable
- [ ] Confidence field populated correctly

**Exit check:** `POST /diagnose` with a sample incident description returns valid JSON DiagnosisResponse with evidence citations.

#### M1.4 — Benchmark pipeline works (Week 2–3)

- [ ] `POST /benchmark/run` triggers 3 request types: cold, shared_prefix, no_shared_prefix
- [ ] Per-request metrics captured: TTFT, total_latency_ms, tokens_per_second
- [ ] BenchmarkRun document stored in MongoDB
- [ ] `GET /benchmark/latest` returns comparison table
- [ ] Cold-start vs. shared-prefix TTFT difference is measurable and documented

**Exit check:** Two successive benchmark runs produce results within 15% of each other. Shared-prefix TTFT ≤ 60% of cold-start TTFT.

#### M1.5 — Phase 1 completion (Week 3)

- [ ] `./scripts/smoke_test.sh` passes end-to-end
- [ ] `uv run pytest` passes for all unit + integration tests
- [ ] `ruff check` and `mypy` pass with no errors
- [ ] Phase 1 benchmark report saved to `docs/benchmark_phase1.md`
- [ ] README Quick Start validated on clean AutoDL instance

### Key technical decisions locked in Phase 1

- Prompt Layer 1 content and token budget (do not change without creating a new prompt version)
- Embedding model (switching changes all stored vectors — requires re-ingestion)
- MongoDB collection schema for `chunks` and `benchmark_runs`
- DiagnosisResponse JSON schema (changing it breaks any downstream consumer)

---

## Phase 2 — Service Hardening

### Objective

Make the system more robust and demo-friendly without changing the core performance proof. Add async ingestion, streaming responses, and a metrics panel.

### Scope additions

#### 2.1 — Async Kafka ingestion

- Activate Kafka in docker-compose (already declared as stub)
- `services/ingestion` becomes a Kafka consumer (replace sync HTTP handler)
- `POST /documents` publishes `faultatlas.documents.uploaded` and returns immediately
- Document status tracked via `ingestion:status:{id}` in Redis (already designed)
- DLQ pattern for failed ingestion jobs

**Trigger condition:** Document upload latency > 3s for large files in Phase 1 demo.

#### 2.2 — Async benchmark tasks

- `POST /benchmark/run` returns a task ID immediately
- Background task runs benchmark, writes progress to Redis
- `GET /benchmark/{run_id}/status` polls progress
- Prevents HTTP timeout for long benchmarks

#### 2.3 — Streaming diagnosis responses

- Add `stream=true` param to `POST /diagnose`
- FastAPI StreamingResponse + SSE
- Useful for demo UX — shows tokens arriving in real time

#### 2.4 — Metrics and observability

- Add `/metrics` Prometheus endpoint to `api` and `retriever`
- Activate `docker-compose.obs.yml` (Prometheus + Grafana + Loki)
- Key metrics to expose:
  - `faultatlas_diagnosis_latency_ms` (histogram)
  - `faultatlas_ttft_ms` (histogram, labeled by `request_type`)
  - `faultatlas_prefix_cache_hit_ratio` (gauge, estimated from TTFT delta)
  - `faultatlas_retrieval_cache_hit_total` (counter)

#### 2.5 — Retrieval quality improvements

- Hybrid BM25 + vector search (MongoDB Atlas text search or in-memory)
- Cross-encoder re-ranking (lightweight model)
- Retrieval precision@k metric in benchmark report

### Phase 2 exit criteria

- End-to-end document upload is fully async; HTTP response < 200ms
- Streaming diagnosis works in browser (EventSource demo)
- Grafana dashboard shows TTFT histogram with shared/cold split
- Hybrid retrieval improves top-1 precision on 10 test queries vs. Phase 1

---

## Phase 3 — Cloud-native Packaging

### Objective

Package the system for deployment beyond a single AutoDL instance. Enable it to be presented as a production-capable platform, not just a demo.

### Scope additions

#### 3.1 — Helm chart

- Convert `infra/k8s/` raw manifests to Helm chart with `values.yaml`
- Separate values files: `values.dev.yaml`, `values.prod.yaml`
- Named chart: `faultatlas`

#### 3.2 — HPA + resource tuning

- Activate `infra/k8s/hpa/` manifests
- Define resource requests/limits based on Phase 1/2 profiling data
- `ingestion` HPA driven by Kafka consumer lag (KEDA)

#### 3.3 — Secrets management

- Replace `.yaml.tmpl` with sealed-secrets or external-secrets-operator integration
- Document secrets rotation procedure

#### 3.4 — Multi-GPU / distributed SGLang

- SGLang tensor parallelism config for 2x GPU setup
- Benchmark multi-GPU throughput vs. single-GPU Phase 1 baseline

#### 3.5 — Production observability

- Full OpenTelemetry distributed tracing (trace: upload → chunk → embed → retrieve → diagnose)
- Alerting rules in Prometheus (TTFT p95 > threshold, OOM events)
- Log correlation via trace ID across services

#### 3.6 — Authentication layer

- API key per user/team (replace single shared key)
- JWT validation middleware
- Per-key rate limiting in Redis

### Phase 3 exit criteria

- `helm install faultatlas ./infra/helm` deploys cleanly to a K8S cluster
- OTel trace visible end-to-end in Grafana Tempo for a single `/diagnose` request
- JWT auth rejects unauthenticated requests; API key rate limiting works

---

## What Is Never in Scope

The following are out of scope for all three phases and belong to a separate commercial product roadmap:

| Feature | Reason |
|---|---|
| Real-time log agent (tail + parse + alert) | Fundamentally different product; would require dedicated streaming pipeline team |
| Multi-tenant SaaS | Requires data isolation, billing, and compliance work beyond demo scope |
| Fine-tuning on customer incident data | Requires data governance, feedback pipeline, and dedicated training infra |
| Automated remediation execution | Changes the risk profile entirely — requires change management integration |
| Custom embedding model training | Out of scope for validated RAG demo; embedding quality is not the bottleneck |

See [`docs/adr/ADR-003-commercial-evolution.md`](adr/ADR-003-commercial-evolution.md) for commercial roadmap.

---

## Dependency Map

```
Phase 1 ──────────────────────────────────────────────► Phase 2 ──► Phase 3
│                                                         │
│ Unlocks:                                                │ Unlocks:
│  - Phase 2 Kafka activation (stub already in place)    │  - Phase 3 Helm (K8S stubs ready)
│  - Phase 2 metrics (Prometheus stubs in compose)       │  - Phase 3 multi-GPU (single-GPU baseline needed)
│  - Commercial Phase 1 auth (API key stub ready)        │
│                                                         │
└─ Phase 1 benchmark report is INPUT to commercial       └─ Phase 2 Grafana is INPUT to Phase 3 alerting
   pitch deck and customer conversations
```

---

## Risk Register

| Risk | Phase | Mitigation |
|---|---|---|
| SGLang OOM on RTX 4090 with Qwen2.5-7B at 12k context | Phase 1 | Set `--mem-fraction-static 0.88`, test 8k first; fall back to Qwen3-4B |
| Prefix cache hit rate lower than expected | Phase 1 | Audit prompt Layer 1 for any variable tokens; use SGLang cache stats API |
| OpenAI embedding API rate limits during seed | Phase 1 | Batch embeddings (100/call already implemented); add retry with backoff |
| Kafka complexity delays benchmark | Phase 2 | Kafka is Phase 2 only; Phase 1 is explicitly HTTP-sync |
| K8S manifests become stale vs. compose | Phase 3 | K8S is stubs only until Phase 3; don't maintain parity earlier |
