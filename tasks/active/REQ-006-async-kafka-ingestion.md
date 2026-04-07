---
req_id: REQ-006
title: Async Kafka ingestion pipeline
status: draft
phase: phase-2
milestone: M2.1
priority: P1
depends_on: [REQ-001]
owner: danielwong
---

# User Story

As a knowledge base administrator, when I upload a large batch of documents, I want the upload HTTP response to return immediately (< 500ms) while ingestion happens asynchronously, so that large files don't time out the HTTP connection and I can upload multiple documents in parallel.

# Goal

Activate the Kafka-based async ingestion pipeline that was stubbed in Phase 1. `POST /documents` becomes a thin publisher; `services/ingestion` becomes a Kafka consumer worker. This is triggered when upload latency > 3s for large files becomes a demo blocker.

Phase 1 synchronous behavior is replaced, not extended. The idempotency, error handling, and chunking logic from REQ-001 are preserved; only the execution model changes.

# AI Behavior Definition

## Capability
- Same extraction / chunking / embedding logic as REQ-001
- **New:** decoupled execution — upload publishes `DocumentUploaded` event; consumer processes it
- Status polling via `GET /documents/{id}/status` is the primary feedback mechanism

## Boundary
- Must NOT lose a document if the consumer crashes mid-processing — Kafka offset is committed only after successful MongoDB write
- Must NOT process the same document twice in parallel — use Redis distributed lock (`ingestion:lock:embed:{document_id}`)

## Fallback / Degradation
- Kafka unavailable at upload time → fall back to synchronous processing (Phase 1 behavior), log warning
- Consumer DLQ: after 3 failed attempts, publish to `faultatlas.dlq.documents.uploaded`, mark document `failed`

# Deliverables

- [ ] Activate Kafka consumer in `services/ingestion/app/main.py`
- [ ] `POST /documents` publishes event and returns immediately (< 500ms)
- [ ] DLQ consumer: reads from DLQ, marks document `failed`, alerts via log
- [ ] Update `scripts/create_topics.sh` to verify topics exist before starting consumer
- [ ] Integration test: upload → verify async processing → verify indexed status

# Acceptance Criteria

1. `POST /documents` returns within 500ms for any file size ≤ 50MB
2. After uploading, `GET /documents/{id}/status` eventually returns `indexed` (within 60s for a 10-page PDF)
3. Killing the consumer mid-embedding and restarting resumes from the correct Kafka offset — no duplicate chunks

# Eval Design

```bash
# Verify async response time
time curl -X POST http://localhost:8000/documents -H "X-API-Key: ..." -F "file=@large_doc.pdf"
# Expected: response in < 500ms

# Verify eventual indexing
sleep 30 && curl http://localhost:8000/documents/{id}/status
# Expected: {"status": "indexed"}
```

# Model / Data Dependencies

- Kafka topics must exist (run `scripts/create_topics.sh` first)
- REQ-001 chunking/embedding logic unchanged

# Out of Scope

- Real-time log streaming from external systems
- Kafka Schema Registry / Avro

# Notes for CodeX Review

- Verify Kafka offset commit happens AFTER MongoDB write, not before
- Check: does the fallback to sync processing work correctly when Kafka is down?
- Verify DLQ consumer marks document as `failed` — not `pending` indefinitely
