# ADR-002 — Technology Selection

| Field | Value |
|---|---|
| **Status** | Accepted |
|**Date** | 2026-04-07 |
| **Deciders** | danielwong |

---

## Context

This ADR documents the technology choices for FaultAtlas Phase 1 MVP and the reasoning behind each. It is not a comprehensive survey — it focuses on decisions where there was a meaningful alternative and the choice has architectural consequences.

---

## Decision 1 — LLM Serving: SGLang over vLLM / llama.cpp / direct Transformers

### Decision
Use **SGLang** as the local LLM serving framework.

### Rationale

| Criterion | SGLang | vLLM | llama.cpp |
|---|---|---|---|
| Prefix caching (KV reuse) | RadixAttention — first-class, tree-structured | Prefix caching available but less granular | CPU-focused, limited prefix opt |
| OpenAI-compatible API | Yes, built-in | Yes, built-in | Via server wrapper |
| Qwen2.5 support | Confirmed | Confirmed | Confirmed |
| Continuous batching | Yes | Yes | Limited |
| Tensor parallelism | Yes | Yes | No |
| Python ecosystem fit | High (PyPI) | High (PyPI) | C++ binary |

The core reason to use SGLang specifically is **RadixAttention** — a trie-based KV cache that matches prefix tokens across requests at a finer granularity than page-level caching. This is the mechanism we are benchmarking. Using vLLM would test a different (less aggressive) prefix cache; using llama.cpp would not test it at all.

### Consequence

The benchmark in Phase 1 is specifically measuring SGLang RadixAttention behavior. Results should be reported as "SGLang RadixAttention on RTX 4090" not "prefix caching in general." vLLM comparison is a Phase 2 optional addition.

---

## Decision 2 — Model: Qwen2.5-7B-Instruct (primary) / Qwen3-8B (alternative)

### Decision
Use **Qwen2.5-7B-Instruct** as the primary model. Allow **Qwen3-8B** as an alternative if available.

### Rationale

| Criterion | Qwen2.5-7B-Instruct | Qwen3-8B | GPT-4o-mini (API) | Llama-3.1-8B |
|---|---|---|---|---|
| Fits in 4090 24GB | Yes (~16 GB at bf16) | Yes (~18 GB at bf16) | N/A (remote) | Yes |
| Instruction following quality | Strong | Strong (latest) | Strong | Good |
| Structured JSON output | Reliable | Reliable | Very reliable | Moderate |
| Chinese log content support | Excellent | Excellent | Good | Limited |
| Local deployment | Yes | Yes | No | Yes |
| SGLang compatibility | Confirmed | Confirmed | N/A | Confirmed |

Qwen models are chosen specifically because:
1. They fit comfortably on a single 4090 at bf16 with headroom for the KV cache
2. They handle mixed Chinese/English log content well (likely in incident logs from Chinese infrastructure)
3. Both are confirmed SGLang-compatible with tested configs

GPT-4o-mini is supported as the **OpenAI API fallback mode** (`LLM_BACKEND=openai`). This is a design requirement — the system must be runnable without GPU hardware for development and CI purposes.

### Consequence

The embedding model remains OpenAI `text-embedding-3-small` in Phase 1 (external API). This keeps the local inference concern focused on generation, not retrieval. A local embedding model (e.g., `BAAI/bge-m3`) is a Phase 2 option when offline operation is required.

---

## Decision 3 — Vector Store: MongoDB (in-process cosine, Phase 1) → Atlas Vector Search (Phase 2+)

### Decision
Phase 1 uses **in-memory cosine similarity over MongoDB-stored embeddings**. Phase 2+ migrates to **MongoDB Atlas Vector Search** or a dedicated vector DB.

### Rationale

The MVP is running on a single AutoDL machine. Introducing a separate vector database (Weaviate, Qdrant, Pinecone) adds:
- Another service to run in docker-compose
- Another client library in `shared/`
- Another failure mode
- Setup friction for a first-time engineer running the demo

For the Phase 1 knowledge base size (tens to low hundreds of documents), in-memory cosine similarity over ~1k–10k chunks is fast enough (<50ms retrieval). The retrieval performance is not what we are benchmarking in Phase 1.

The MongoDB chunk storage schema (`embedding` field inline on chunk documents) is designed to be forward-compatible with MongoDB Atlas Vector Search `$vectorSearch` aggregation stage — the migration is a one-line query change plus an index definition.

### Consequence

Phase 1 retrieval does not scale beyond ~50k chunks without latency degradation. This is acceptable for a demo knowledge base. Any deployment intending to index > 10k documents should activate Atlas Vector Search before going live.

---

## Decision 4 — Async pipeline: HTTP-sync in Phase 1, Kafka in Phase 2

### Decision
Phase 1 ingestion is **synchronous HTTP** (upload → process → return). Kafka is declared in docker-compose and the shared library but **not used** in Phase 1 application code.

### Rationale

Kafka adds correctness and scalability benefits (replayability, backpressure, consumer group parallelism) that are not needed for a demo knowledge base built from manual uploads. The complexity it adds (consumer group management, offset tracking, DLQ handling) would consume ~1 week of a 3-week Phase 1.

More importantly: Kafka does not affect the benchmark. The performance hypothesis is about LLM serving latency, not ingestion throughput.

The Kafka topic definitions, producer/consumer wrappers, and event schemas are already implemented in `shared/faultatlas/kafka/`. Activating Kafka in Phase 2 means wiring the consumer in `services/ingestion/app/main.py` — the infrastructure is ready.

### Consequence

In Phase 1, `POST /documents` blocks until ingestion completes. For large files (>10 MB) or many concurrent uploads, this will cause timeouts. This is acceptable for a demo with pre-selected sample files. If this becomes a problem during Phase 1 demo prep, the mitigation is to upload files one at a time via the seed script.

---

## Decision 5 — Application framework: FastAPI

### Decision
Use **FastAPI** for all HTTP services (`api`, `retriever`).

### Rationale

- Native async (`async def`) compatible with Motor (async MongoDB) and async Redis
- Pydantic v2 integration is first-class — schemas double as API docs and runtime validation
- Auto-generated OpenAPI / Swagger UI — essential for a demo without a frontend
- `fastapi dev` command provides hot reload in development
- Well-understood by the Python ML/backend engineering audience this project targets

No alternative was seriously considered. Flask/Django are sync-first; aiohttp requires more boilerplate. FastAPI is the dominant choice for this use case.

---

## Decision 6 — Python environment: uv workspaces

### Decision
Use **uv** for Python environment management, with a monorepo workspace configuration.

### Rationale

- `uv sync --all-packages` installs all services' dependencies in one command — critical for DX on a fresh AutoDL instance
- `uv run --package faultatlas-api` scopes execution to a specific service without activating/deactivating venvs
- Workspace `path = { workspace = true }` for `faultatlas-shared` ensures the shared library is always the local version, never a stale PyPI publish
- Significantly faster than pip for dependency resolution (Rust-based resolver)
- `uv.lock` provides fully reproducible builds across machines and CI

### Consequence

All contributors must have `uv` installed. The Dockerfiles use `pip install uv` as the bootstrap step. This is a minor additional setup step but is outweighed by the DX improvements.

---

## Decision 7 — Infrastructure: Docker Compose (Phase 1), K8S stubs (Phase 3)

### Decision
Phase 1 runs entirely on **Docker Compose** on a single AutoDL machine. Kubernetes manifests exist as stubs and are **not the primary deployment target** until Phase 3.

### Rationale

The performance benchmark requires controlling the environment precisely. K8S scheduling, resource management, and network overlay add variance to latency measurements. Docker Compose on bare metal (AutoDL) gives the cleanest measurement environment for Phase 1.

K8S stubs (`infra/k8s/`) are maintained as valid manifests but not tested until Phase 3. They exist to demonstrate architectural intent, not to run.

### Consequence

AutoDL instance costs are pay-per-hour. The Phase 1 docker-compose stack is designed to start from scratch in under 5 minutes (`docker compose up --build`), minimizing cost from idle instances.

---

## Summary Table

| Decision | Chosen | Key reason | Revisit condition |
|---|---|---|---|
| LLM serving | SGLang | RadixAttention prefix caching | Phase 2: add vLLM comparison |
| Model | Qwen2.5-7B-Instruct | Fits 4090, good JSON output, Chinese support | Phase 3: multi-GPU, larger model |
| Vector store | MongoDB in-memory (Phase 1) | Zero extra service, forward-compatible schema | Phase 2: Atlas Vector Search |
| Ingestion pipeline | HTTP-sync (Phase 1) | Kafka complexity not needed for benchmark | Phase 2: activate Kafka consumer |
| API framework | FastAPI | Async-native, Pydantic v2, Swagger UI | Not revisited |
| Python env | uv workspaces | Fast, reproducible, monorepo-friendly | Not revisited |
| Infrastructure | Docker Compose | Lowest latency variance for benchmark | Phase 3: Helm + K8S |
