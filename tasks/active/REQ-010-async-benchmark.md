---
req_id: REQ-010
title: Async benchmark task queue
status: draft
phase: phase-2
milestone: M2.2
priority: P2
depends_on: [REQ-005]
owner: danielwong
---

# User Story

As a developer running the benchmark, I want `POST /benchmark/run` to return immediately with a task ID so that the HTTP connection doesn't time out during a long 15-run benchmark, and I can poll for results or check progress.

# Goal

Phase 1 benchmark runs synchronously and can take 3–5 minutes. This causes HTTP timeouts on AutoDL's proxy layer. Make it async using a background task + Redis for state, without introducing Celery or a separate task queue service.

# AI Behavior Definition

No AI behavior — async task management infrastructure.

# Deliverables

- [ ] `POST /benchmark/run` returns `{ run_id, status: "started" }` immediately
- [ ] FastAPI `BackgroundTasks` runs the benchmark in the background
- [ ] `GET /benchmark/{run_id}/progress` returns live status from Redis
- [ ] Redis key: `benchmark:run:{run_id}` stores `{ status, completed_runs, total_runs, partial_results? }`
- [ ] On completion, results written to MongoDB `benchmark_runs`

# Acceptance Criteria

1. `POST /benchmark/run` responds in < 1s
2. `GET /benchmark/{run_id}/progress` shows increasing `completed_runs` during execution
3. `GET /benchmark/latest` returns the completed report after background task finishes

# Eval Design

```bash
RUN_ID=$(curl -s -X POST http://localhost:8000/benchmark/run -H "X-API-Key: ..." | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
sleep 5
curl http://localhost:8000/benchmark/$RUN_ID/progress
# Should show completed_runs > 0 and < total_runs
```

# Model / Data Dependencies

- REQ-005: benchmark runner logic unchanged, just wrapped in BackgroundTasks

# Out of Scope

- Celery / Redis Queue task broker
- Benchmark cancellation

# Notes for CodeX Review

- Verify FastAPI BackgroundTasks exception handling — unhandled exceptions in background tasks are silently swallowed; ensure errors update Redis state and MongoDB
