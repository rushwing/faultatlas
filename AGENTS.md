# AGENTS.md

This file provides guidance to Codex when working in this repository.
Read this before doing anything else in a new session.

## What this project is

**FaultAtlas** is a single-machine, low-latency Incident RAG Copilot. The core purpose is to validate that SGLang's RadixAttention prefix caching produces measurably lower TTFT on repeated-prefix RAG workloads, using a Qwen2.5-7B-Instruct (or Qwen3-8B) model on a single RTX 4090.

This is a **performance proof-of-concept with a minimal application wrapper** — not a feature-complete platform.

## Phase 1 boundary — read before touching any code

Phase 1 is the only active phase. The following are **stubs that must not be activated** without updating `docs/MVP_SCOPE.md` and `docs/adr/ADR-001-mvp-scope-definition.md`:

| Component | Status in Phase 1 | Where the stub lives |
|---|---|---|
| Kafka consumers/producers | **OFF** — not called by application code | `shared/faultatlas/kafka/` |
| Kubernetes manifests | **OFF** — not a deployment target | `infra/k8s/` |
| Prometheus/Grafana | **OFF** — structured logs only | `infra/compose/docker-compose.obs.yml` |
| Multi-hop agent / planner | **OFF** | Not implemented |
| Streaming SSE responses | **OFF** | Not implemented |

If a task seems to require activating any of the above, pause and confirm with the user before proceeding.

## Key commands

```bash
# Install all dependencies
uv sync --all-packages

# Start infrastructure (MongoDB + Redis)
make infra-up

# Run services with hot reload (local dev)
make local-api        # port 8000
make local-retriever  # port 8001

# Run all tests
make test

# Lint + typecheck
make check

# AutoDL full deploy
make setup-autodl

# SGLang server management
make sglang-start / sglang-stop / sglang-status / sglang-logs
```

## Repository layout (important boundaries)

```
shared/faultatlas/    ← installable library; each service imports this
services/api/         ← HTTP gateway + agent orchestrator (port 8000)
services/retriever/   ← internal vector search (port 8001, not public)
services/ingestion/   ← document pipeline worker (sync HTTP in Phase 1)
infra/compose/        ← docker-compose (core + obs overlay + override)
infra/docker/         ← Dockerfiles per service
infra/k8s/            ← K8S stubs ONLY, Phase 3
infra/env/            ← env templates per deployment target
docs/MVP_SCOPE.md     ← authoritative scope index
docs/MVP_DEV_PHASES.md← phase milestones and exit criteria
docs/adr/             ← architecture decisions (ADR-001 through ADR-004)
tasks/                ← active work items and handoff notes (REQ-001~015)
scripts/deploy/       ← AutoDL and WSL2 setup scripts
harness/              ← AI quality evals (distinct from tests/)
harness/evals/rag/    ← RAGAS: faithfulness, context precision, recall
harness/evals/agent/  ← DeepEval: hallucination, schema validity, calibration
harness/evals/prompt/ ← Prompt stability + regression vs baseline
harness/evals/model/  ← Model comparison (Qwen2.5 vs Qwen3 vs GPT-4o-mini)
harness/datasets/     ← Golden sets and fixtures (source of truth for evals)
```

## Architecture constraints that must not be broken

### 1. Prompt structure is load-bearing for the benchmark

The diagnosis prompt **must** follow this 3-layer order, always:

```
Layer 1 — system prefix     (fixed, ~800 tokens, never variable content)
Layer 2 — context scaffold  (retrieved chunks, deterministic ordering)
Layer 3 — user query        (variable, appended last)
```

Breaking this structure (injecting timestamps, random IDs, or dynamic content into Layer 1; shuffling chunk order in Layer 2) will destroy prefix cache hit rate and invalidate the benchmark.

Prompt template lives in `services/api/app/agents/prompts.py`. Do not add variable content to the system prompt without explicit user confirmation.

### 2. LLM backend is switchable via `LLM_BACKEND` env var

- `LLM_BACKEND=sglang` → calls SGLang at `SGLANG_BASE_URL`
- `LLM_BACKEND=openai` → calls OpenAI API

Application code must never hardcode either path. The switch point is in `services/api/app/agents/orchestrator.py`.

### 3. `shared/` is the only place for cross-service code

Never put shared logic directly into a service. If something is needed by two services:
1. Add it to `shared/faultatlas/`
2. Update `shared/pyproject.toml` if a new dependency is required
3. Both services already declare `faultatlas-shared = { workspace = true }`

### 4. Redis is ephemeral, MongoDB is authoritative

Nothing stored in Redis is source-of-truth. If Redis data conflicts with MongoDB, MongoDB wins. Do not design flows that require Redis to be consistent with MongoDB.

### 5. `DiagnosisResponse` schema is stable

The `DiagnosisResponse` JSON schema is used by the benchmark pipeline and any external consumer. Do not add or remove fields without versioning. Fields: `session_id`, `summary`, `suspected_causes`, `evidence`, `next_actions`, `confidence`, `latency_ms`, `tokens_used`, `prefix_cache_hint`.

## MongoDB collections and Redis key conventions

Collections defined in `shared/faultatlas/mongo/client.py::Collections`:
`documents`, `chunks`, `incidents`, `citations`, `benchmark_runs`, `agent_sessions`, `audit_log`

Redis key patterns defined in `shared/faultatlas/redis/client.py::RedisKeys`:
```
api:session:{session_id}              TTL 30m
retriever:query_cache:{query_hash}    TTL 5m
ingestion:status:{document_id}        TTL 1h
ingestion:idempotency:{doc_hash}      TTL 24h
benchmark:run:{run_id}                TTL 1h
```

## Kafka topics (stub — not active in Phase 1)

Topic names live in `shared/faultatlas/kafka/topics.py::Topics`. The naming convention is `faultatlas.{entity}.{past_tense}`. DLQ pattern: `faultatlas.dlq.{original-topic}`. Do not create new topics without adding them to `Topics`.

## Testing vs Eval — critical distinction

```
tests/             → Software correctness (pytest, fast, runs in CI)
                     "Does the API return 409 on duplicate upload?"

harness/evals/     → AI output quality (RAGAS + DeepEval, slow, runs before releases)
                     "Is the diagnosis faithful to the retrieved evidence?"
```

Never put AI quality assertions in `tests/`. Never put software correctness checks in `harness/`.

```
tests/unit/        → pure logic, no I/O, no Docker
tests/integration/ → requires real MongoDB + Redis
tests/e2e/         → full stack
```

Run unit tests: `uv run pytest -m "not integration"`
Run eval smoke: `make eval-smoke`  (requires services running)
Run full eval:  `make eval`        (5–15 min, before milestone releases)

## Dependency management

- Each service has its own `pyproject.toml`. Add service-specific deps there.
- Cross-service deps go in `shared/pyproject.toml`.
- Never `pip install` directly — always `uv add --package <service-name> <dep>`.
- `uv.lock` is committed. Run `uv sync` after pulling.

## Environment files

- `.env.example` — template, always committed, no real secrets
- `.env` — real secrets, never committed (in `.gitignore`)
- `infra/env/.env.autodl` — AutoDL deployment template

## What success looks like for Phase 1

**The benchmark result is the primary deliverable**, not feature completeness.

Target: shared-prefix repeated requests TTFT ≤ 60% of cold-start TTFT on RTX 4090.

The benchmark lives at `POST /benchmark/run` and stores results in the `benchmark_runs` collection.

## Active work items

See `tasks/` for current phase milestones and handoff notes.
Phase 1 milestones: `docs/MVP_DEV_PHASES.md` → Phase 1 section.
