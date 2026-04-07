---
req_id: REQ-009
title: Metrics and Grafana observability
status: draft
phase: phase-2
milestone: M2.4
priority: P1
depends_on: [REQ-005]
owner: danielwong
---

# User Story

As a performance engineer, when I run repeated benchmark sessions over time, I want TTFT and cache hit metrics surfaced in a Grafana dashboard so I can track regressions and improvements across SGLang versions or prompt changes without manually parsing JSON reports.

# Goal

Activate the `docker-compose.obs.yml` observability stack and expose Prometheus metrics from `services/api` and `services/retriever`. Focus on the metrics that matter for the benchmark hypothesis.

# AI Behavior Definition

No AI behavior — purely infrastructure metrics instrumentation.

# Deliverables

- [ ] `GET /metrics` Prometheus endpoint on `api` (port 8000) and `retriever` (port 8001)
- [ ] Key metrics:
  - `faultatlas_diagnosis_latency_ms` histogram (labels: backend, cache_hint)
  - `faultatlas_ttft_ms` histogram (labels: backend, condition)
  - `faultatlas_retrieval_latency_ms` histogram (labels: cache_hit)
  - `faultatlas_retrieval_cache_hit_total` counter
  - `faultatlas_benchmark_run_total` counter (labels: hypothesis_met)
- [ ] `observability/grafana/provisioning/dashboards/faultatlas.json` — pre-provisioned dashboard
- [ ] Dashboard panels: TTFT by condition (bar chart), retrieval cache hit ratio (gauge), benchmark hypothesis trend (time series)
- [ ] `docker compose -f docker-compose.obs.yml up` starts Prometheus + Grafana automatically

# Acceptance Criteria

1. After 3 diagnosis calls, `GET /metrics` returns `faultatlas_diagnosis_latency_ms_bucket` with non-zero counts
2. Grafana dashboard loads without manual configuration (auto-provisioned)
3. After running `POST /benchmark/run`, the TTFT histogram shows 3 condition labels

# Eval Design

```bash
# Smoke test metrics endpoint
curl -s http://localhost:8000/metrics | grep faultatlas_diagnosis_latency
# Should output histogram lines
```

# Model / Data Dependencies

- Phase 1 benchmark data (`benchmark_runs` collection) should be backfilled as Prometheus metrics on startup (optional, nice-to-have)

# Out of Scope

- OpenTelemetry distributed tracing (Phase 3 — REQ-014)
- Alerting rules and PagerDuty integration
- Log aggregation beyond structured JSON (already in place)

# Notes for CodeX Review

- Verify histogram bucket boundaries are appropriate for TTFT range (e.g., 100ms, 250ms, 500ms, 1s, 2s, 5s, 10s)
- Check: does `faultatlas_ttft_ms` use `cache_hint` label from `LLMResponse.prefix_cache_hint`?
