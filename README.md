# FaultAtlas

**A low-latency, prefix-cache-friendly Incident RAG Copilot — built to validate LLM serving performance under constrained single-GPU hardware.**

Upload runbooks, historical incident cases, and log samples. Ask questions about active incidents. Get structured diagnostic results backed by retrieved evidence — with built-in benchmarking to prove SGLang prefix caching works.

> **MVP objective:** Demonstrate that a locally-deployed Qwen2.5-7B-Instruct (or Qwen3-8B) on a single RTX 4090, served via SGLang, can deliver meaningfully lower TTFT and higher throughput on repeated-prefix RAG workloads versus cold-start baselines — using the smallest possible production-quality code path.

---

## Architecture Overview

```
  Upload                Ingest
  runbook/case/log ──► chunk + embed + store (MongoDB)
                                │
                                ▼
  Incident Query ──► Retrieval (top-k) ──► Prompt Builder
                                                  │
                         ┌────────────────────────┘
                         │   Fixed 3-part prompt:
                         │   [system prefix]  ← shared, cached by SGLang
                         │   [context scaffold] ← semi-stable
                         │   [user query]     ← variable, appended last
                         ▼
                   SGLang (OpenAI-compatible)
                   Qwen2.5-7B-Instruct / Qwen3-8B
                   RTX 4090 — RadixAttention prefix cache
                         │
                         ▼
               Structured Diagnosis Response
               { summary, suspected_causes, evidence,
                 next_actions, confidence }
                         │
                         ▼
               Benchmark endpoint captures
               TTFT / tokens-per-second / latency
               per request type (cold / shared-prefix / no-shared-prefix)
```

---

## The Four Core Pipelines

| # | Pipeline | Purpose |
|---|---|---|
| 1 | **Ingest** | Upload runbook/case/log → chunk → embed → store in MongoDB |
| 2 | **Retrieve** | Query → vector search → top-k evidence → fixed prompt |
| 3 | **Diagnose** | SGLang generates structured JSON diagnosis from retrieved context |
| 4 | **Benchmark** | Compare TTFT/throughput: cold vs. shared-prefix vs. no-shared-prefix |

---

## Tech Stack

| Component | Technology | Notes |
|---|---|---|
| LLM serving | **SGLang** | OpenAI-compatible server, RadixAttention prefix caching |
| Model | **Qwen2.5-7B-Instruct** or **Qwen3-8B** | Fits in 4090 24 GB VRAM |
| Hardware | **RTX 4090 (AutoDL)** | Single-GPU constraint is intentional |
| API layer | FastAPI | Diagnosis + Benchmark endpoints |
| Vector store | MongoDB (in-memory cosine, MVP) | Replace with Atlas Vector Search later |
| Cache / state | Redis | Session, retrieval cache, benchmark task state |
| Event bus | Kafka | **Stub in Phase 1** — async ingest in Phase 2 |
| Container | Docker Compose | Single-machine deployment on AutoDL |
| Orchestration | Kubernetes | **Stub manifests only** — Phase 3 |

---

## Quick Start

### Prerequisites

- AutoDL instance with RTX 4090 (or equivalent), CUDA 12.x
- Docker + Docker Compose
- `uv` >= 0.4 ([install](https://docs.astral.sh/uv/))
- SGLang installed in the model container (`pip install sglang[all]`)

### 1. Clone and configure

```bash
git clone <repo>
cd faultatlas
cp .env.example .env
# Required: set SGLANG_BASE_URL and MODEL_NAME (or OPENAI_API_KEY for API mode)
```

### 2. Start infrastructure

```bash
docker compose -f infra/compose/docker-compose.yml up mongo redis -d
```

### 3. Start SGLang model server

```bash
# On the GPU host — adjust model path as needed
python -m sglang.launch_server \
  --model-path Qwen/Qwen2.5-7B-Instruct \
  --host 0.0.0.0 --port 8100 \
  --mem-fraction-static 0.88 \
  --enable-torch-compile
```

### 4. Run services

```bash
uv sync --all-packages

# API + retriever
uv run --package faultatlas-api fastapi dev services/api/app/main.py --port 8000
uv run --package faultatlas-retriever fastapi dev services/retriever/app/main.py --port 8001
```

### 5. Seed knowledge base and run benchmark

```bash
uv run python scripts/seed_data.py          # upload sample runbooks + cases
uv run python scripts/run_benchmark.py      # cold / shared-prefix / no-shared-prefix
```

### 6. Explore

- **API docs:** http://localhost:8000/docs
- **Benchmark report:** `GET /benchmark/latest`

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/documents` | Upload runbook / incident case / log sample |
| `GET` | `/documents/{id}/status` | Check ingestion status |
| `POST` | `/diagnose` | Submit incident query → structured diagnosis |
| `GET` | `/incidents` | List incidents |
| `POST` | `/incidents` | Create incident record |
| `POST` | `/benchmark/run` | Trigger benchmark suite |
| `GET` | `/benchmark/latest` | Retrieve latest benchmark report |
| `GET` | `/health` | Liveness |
| `GET` | `/ready` | Readiness |

### Diagnosis response schema

```json
{
  "session_id": "...",
  "summary": "...",
  "suspected_causes": ["..."],
  "evidence": [{"chunk_id": "...", "content": "...", "score": 0.91}],
  "next_actions": ["..."],
  "confidence": "high",
  "latency_ms": 312,
  "tokens_used": 1840,
  "prefix_cache_hint": "shared"
}
```

---

## Prompt Design Principle

The prompt is deliberately structured in three fixed layers to maximise SGLang RadixAttention cache reuse:

```
┌─────────────────────────────────────────────────────┐
│ LAYER 1 — System prefix (fixed, ~800 tokens)        │  ← highest reuse
│   role definition, output rules, JSON schema,        │
│   citation requirements, risk disclaimers            │
├─────────────────────────────────────────────────────┤
│ LAYER 2 — Context scaffold (semi-stable)            │  ← partial reuse
│   retrieved evidence chunks (top-k)                  │
│   matching runbook sections                          │
│   historical similar cases                          │
├─────────────────────────────────────────────────────┤
│ LAYER 3 — User query (variable, ~50–200 tokens)     │  ← always new
│   incident description / alert text                  │
└─────────────────────────────────────────────────────┘
```

This structure means: for any two queries hitting the same knowledge base with the same system prompt version, Layer 1 tokens are always cache hits. Layer 2 reuse depends on retrieval overlap.

---

## Configuration Reference

All config via environment variables. See `.env.example`.

| Variable | Description | Default |
|---|---|---|
| `LLM_BACKEND` | `sglang` or `openai` | `sglang` |
| `SGLANG_BASE_URL` | SGLang server URL | `http://localhost:8100/v1` |
| `MODEL_NAME` | Model identifier | `Qwen/Qwen2.5-7B-Instruct` |
| `OPENAI_API_KEY` | Used when `LLM_BACKEND=openai` | — |
| `OPENAI_CHAT_MODEL` | OpenAI model name | `gpt-4o-mini` |
| `MONGO_URI` | MongoDB connection | `mongodb://localhost:27017` |
| `REDIS_URL` | Redis URL | `redis://localhost:6379/0` |
| `OPENAI_EMBEDDING_MODEL` | Embedding model | `text-embedding-3-small` |
| `CHUNK_SIZE` | Tokens per chunk | `512` |
| `API_KEY` | Service auth key | `changeme-local-dev` |

> **LLM backend switching:** Set `LLM_BACKEND=openai` and provide `OPENAI_API_KEY` to use the OpenAI API instead of a local SGLang server. All other application code stays the same.

---

## Running Tests

```bash
uv run pytest                              # all tests
uv run pytest services/api/tests/
uv run pytest services/ingestion/tests/
uv run pytest services/retriever/tests/

uv run ruff check .
uv run mypy services/
```

---

## Development Phases

| Phase | Focus | Status |
|---|---|---|
| **Phase 1** | Inference-first MVP — single machine, core 4 pipelines, benchmark | **Current** |
| **Phase 2** | Service hardening — async Kafka ingest, metrics, benchmark history | Planned |
| **Phase 3** | Cloud-native packaging — Helm, HPA, production K8S | Future |

See [`docs/MVP_DEV_PHASES.md`](docs/MVP_DEV_PHASES.md) for full phase breakdown.

---

## Success Criteria

### Functional
- Given an incident query + uploaded knowledge base, the system returns a structured JSON diagnosis with evidence citations
- Repeated queries against the same knowledge base return stable results
- LLM backend is switchable between SGLang (local) and OpenAI API via environment variable

### Performance (the real goal)
- Shared-prefix repeated requests show measurably lower TTFT vs. cold-start baseline
- Shared-prefix TTFT advantage is demonstrable in the benchmark report
- System runs stably on single RTX 4090 with 8k–12k token contexts without OOM
- Continuous serving of 10+ concurrent requests without degradation

---

## Repository Layout

```
faultatlas/
├── services/
│   ├── api/          # FastAPI gateway, agent orchestrator, diagnosis, benchmark
│   ├── ingestion/    # Document pipeline worker (Kafka consumer — Phase 2)
│   └── retriever/    # Internal vector search service
├── shared/           # faultatlas-shared: models, events, Kafka/Mongo/Redis clients
├── infra/
│   ├── docker/       # Dockerfiles per service
│   ├── compose/      # docker-compose (core + obs overlay)
│   └── k8s/          # K8S manifests (stub, Phase 3)
├── docs/
│   ├── MVP_SCOPE.md
│   ├── MVP_DEV_PHASES.md
│   └── adr/          # Architecture Decision Records
├── observability/    # Prometheus + Loki configs
├── scripts/          # seed_data.py, run_benchmark.py, smoke_test.sh
└── tests/            # Integration + e2e
```

See [`docs/MVP_SCOPE.md`](docs/MVP_SCOPE.md) for the full scope index.
See [`docs/adr/`](docs/adr/) for architecture decisions.

---

## Reset local dev

```bash
./scripts/reset_dev.sh
```
