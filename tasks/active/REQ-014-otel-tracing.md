---
req_id: REQ-014
title: Full OpenTelemetry distributed tracing
status: draft
phase: phase-3
milestone: M3.5
priority: P1
depends_on: [REQ-009]
owner: danielwong
---

# User Story

As a platform engineer debugging a slow diagnosis request, I want to see a distributed trace that shows how time was spent across the upload → retrieve → diagnose pipeline (broken down by service and operation), so I can identify bottlenecks without manually correlating timestamps from three separate log files.

# Goal

Instrument all three services (`api`, `retriever`, `ingestion`) with OpenTelemetry and export traces to Grafana Tempo (or Jaeger). A single `POST /diagnose` request should produce a trace showing: retrieval latency, LLM TTFT, prompt build time, MongoDB write time.

# AI Behavior Definition

No AI behavior — observability instrumentation.

## Boundary
- Must NOT include raw prompt content or user query in trace attributes — PII/confidentiality risk
- Trace attributes may include: `session_id`, `document_count`, `chunk_count`, `ttft_ms`, `tokens_used`, `prefix_cache_hint`

# Deliverables

- [ ] `opentelemetry-sdk` + `opentelemetry-exporter-otlp` added to all three service `pyproject.toml`
- [ ] Auto-instrumentation for FastAPI (opentelemetry-instrumentation-fastapi) and Motor (opentelemetry-instrumentation-motor)
- [ ] Manual span for LLM call with `ttft_ms` and `prefix_cache_hint` attributes
- [ ] Trace context propagated via HTTP headers (`traceparent`) between `api` → `retriever`
- [ ] `correlation_id` in audit log linked to OTel `trace_id`
- [ ] Grafana Tempo added to `docker-compose.obs.yml`
- [ ] Grafana dashboard: trace view for a single diagnosis request

# Acceptance Criteria

1. A single `POST /diagnose` produces a trace with ≥ 4 spans: `api.diagnose`, `retriever.search`, `llm.complete`, `mongo.write_session`
2. `trace_id` appears in the audit log entry for that request
3. Grafana Tempo shows the trace within 10s of the request completing

# Eval Design

```bash
# Make a diagnosis request
SESSION_ID=$(curl -s -X POST http://localhost:8000/diagnose ... | python3 -c "import sys,json; print(json.load(sys.stdin)['session_id'])")

# Check trace in Tempo via Grafana API
curl "http://localhost:3000/api/datasources/proxy/1/api/search?tags=session_id%3D${SESSION_ID}"
# Should return at least 1 trace
```

# Model / Data Dependencies

- Grafana Tempo added to observability stack
- `correlation_id` field already exists on `agent_sessions` documents — link to `trace_id`

# Out of Scope

- Metrics from OTel (Prometheus is already handling metrics)
- Log aggregation via OTel (Loki via Promtail is already in place)
- Sampling configuration (100% sampling is acceptable for Phase 3 demo)

# Notes for CodeX Review

- Verify user query text does NOT appear in any span attribute
- Check trace context propagation: does `api` → `retriever` HTTP call carry `traceparent` header?
