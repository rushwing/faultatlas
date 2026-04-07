# Tasks

Feature stories for FaultAtlas Phase 1–3.

## Structure

```
tasks/
  active/          ← current sprint items
  done/            ← completed (moved here after merge)
  TEMPLATE.md      ← story template
  README.md        ← this file
```

## Story index

### Phase 1 — Inference-first MVP

| ID | Title | Status | Milestone |
|---|---|---|---|
| [REQ-001](active/REQ-001-document-ingestion.md) | Document ingestion pipeline | draft | M1.1 |
| [REQ-002](active/REQ-002-vector-retrieval.md) | Vector retrieval service | draft | M1.2 |
| [REQ-003](active/REQ-003-sglang-integration.md) | SGLang model server integration | draft | M1.3 |
| [REQ-004](active/REQ-004-diagnosis-endpoint.md) | Structured diagnosis endpoint | draft | M1.3 |
| [REQ-005](active/REQ-005-benchmark-pipeline.md) | Prefix cache benchmark pipeline | draft | M1.4 |

### Phase 2 — Service Hardening

| ID | Title | Status | Milestone |
|---|---|---|---|
| [REQ-006](active/REQ-006-async-kafka-ingestion.md) | Async Kafka ingestion pipeline | draft | M2.1 |
| [REQ-007](active/REQ-007-streaming-diagnosis.md) | Streaming diagnosis responses (SSE) | draft | M2.2 |
| [REQ-008](active/REQ-008-hybrid-retrieval.md) | Hybrid BM25 + vector retrieval | draft | M2.5 |
| [REQ-009](active/REQ-009-observability.md) | Metrics and Grafana observability | draft | M2.4 |
| [REQ-010](active/REQ-010-async-benchmark.md) | Async benchmark task queue | draft | M2.2 |

### Phase 3 — Cloud-native Packaging

| ID | Title | Status | Milestone |
|---|---|---|---|
| [REQ-011](active/REQ-011-helm-chart.md) | Helm chart packaging | draft | M3.1 |
| [REQ-012](active/REQ-012-auth-layer.md) | Authentication layer (JWT + RBAC) | draft | M3.6 |
| [REQ-013](active/REQ-013-multi-gpu-sglang.md) | Multi-GPU SGLang configuration | draft | M3.4 |
| [REQ-014](active/REQ-014-otel-tracing.md) | Full OpenTelemetry tracing | draft | M3.5 |
| [REQ-015](active/REQ-015-secrets-management.md) | Production secrets management | draft | M3.3 |

## Status lifecycle

```
draft → ready → in_progress → review → done
                                  ↓
                              cancelled
```

- `draft`: written, not yet reviewed
- `ready`: reviewed by human + CodeX, approved for implementation
- `in_progress`: Claude Code is implementing
- `review`: implementation done, pending CodeX code review
- `done`: merged, move file to `done/`

## File naming

`REQ-{NNN}-{short-slug}.md`

## Relationship to docs/

- `docs/MVP_SCOPE.md` — authoritative in/out of scope
- `docs/MVP_DEV_PHASES.md` — milestone exit criteria (source of truth for "done")
- `docs/adr/` — architectural decisions (if a story reveals a new arch decision, write an ADR)
- `tasks/` — operational stories for implementation and handoff
