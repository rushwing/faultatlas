---
req_id: REQ-001
title: Document ingestion pipeline
status: draft
phase: phase-1
milestone: M1.1
priority: P0
depends_on: []
owner: danielwong
---

# User Story

As a knowledge base administrator, when I upload a runbook, historical incident case, or log sample (PDF or plain text), I want the system to automatically extract, chunk, and embed the content into the knowledge base so that it becomes immediately available for retrieval-augmented diagnosis.

# Goal

Build the foundational ingestion pipeline. Without this, the retrieval and diagnosis pipelines have nothing to work with. Phase 1 scope is intentionally narrow: synchronous HTTP upload, fixed-size chunking, OpenAI embedding API. No real-time streaming, no AI-adaptive chunking (that is Phase 2+).

# AI Behavior Definition

## Capability
- **Perceive:** raw file bytes + content type (PDF or plain text)
- **Decide:** extract text deterministically (pypdf for PDF, utf-8 decode for text), then chunk using `RecursiveCharacterTextSplitter` with configurable `CHUNK_SIZE` / `CHUNK_OVERLAP`
- **Generate:** a batch of OpenAI embedding vectors (100 chunks per API call), stored inline on chunk documents
- **Interaction paradigm:** synchronous HTTP — `POST /documents` blocks until all chunks are indexed; status is also queryable via `GET /documents/{id}/status`

## Boundary
- Must NOT silently drop chunks if the embedding API fails mid-batch — mark document status as `failed`, store error in document record, return 500 with `error_detail`
- Must NOT create duplicate chunks if the same file is uploaded twice — enforce idempotency via `SHA-256(content)` key in Redis (24h TTL), return 409 on collision
- Must NOT store raw file bytes in MongoDB — store only extracted text and metadata; binary storage is out of scope for Phase 1
- Must NOT attempt OCR on scanned PDFs — extract what pypdf can read, flag unreadable pages in `source_metadata.unreadable_pages`, do not hallucinate content

## Fallback / Degradation
- Encrypted PDF → status `failed`, `error_detail: "encrypted_pdf"`, prompt user to provide plaintext version
- pypdf returns empty string for a page → include page index in `source_metadata.unreadable_pages`, continue with remaining pages
- OpenAI embedding API rate limit (429) → retry with exponential backoff (max 3 attempts), then fail with `error_detail: "embedding_api_unavailable"`
- File > 50 MB → reject at upload with 413, suggest splitting the file

# Deliverables

- [ ] `POST /documents` — upload endpoint with idempotency check
- [ ] `GET /documents/{id}/status` — status polling endpoint
- [ ] `services/ingestion/app/processors/extractor.py` — PDF + text extraction
- [ ] `services/ingestion/app/processors/chunker.py` — RecursiveCharacterTextSplitter wrapper
- [ ] `services/ingestion/app/processors/embedder.py` — batched OpenAI embedding with retry
- [ ] `services/ingestion/app/storage/mongo.py` — save_chunks(), update_document_status()
- [ ] `services/ingestion/app/consumers/document_upload.py` — pipeline orchestrator
- [ ] Unit tests: chunker, extractor, idempotency logic
- [ ] Integration test: upload → verify chunks in MongoDB

# API Contract

```
POST /documents
Headers:  X-API-Key: {key}
Body:     multipart/form-data  file={binary}
Response 200: { document_id, status: "pending", message }
Response 409: { detail: "Document already submitted" }
Response 413: { detail: "File exceeds 50MB limit" }
Response 500: { detail: "...", error_detail: "embedding_api_unavailable|encrypted_pdf|..." }

GET /documents/{document_id}/status
Response 200: { document_id, status: "pending|chunking|embedding|indexed|failed", error_detail? }
```

MongoDB document schema (`chunks` collection):
```json
{
  "_id": "uuid",
  "document_id": "uuid",
  "content": "text",
  "chunk_index": 0,
  "token_count": 120,
  "embedding": [0.01, ...],
  "embedding_model": "text-embedding-3-small",
  "created_at": "ISO8601"
}
```

# Acceptance Criteria

## Functional
1. Given a valid PDF runbook, when uploaded, then `GET /documents/{id}/status` returns `indexed` and `db.chunks.countDocuments({document_id})` > 0
2. Given the same file uploaded twice, the second upload returns HTTP 409
3. Given an encrypted PDF, status is `failed` and `error_detail` is `encrypted_pdf`
4. Given a plain text log file, all newline-separated log entries appear in at least one chunk

## Performance / Quality
- Ingestion of a 50-page PDF completes in < 60s on AutoDL (embedding API latency dominates)
- Chunk count for a 10-page runbook: between 20 and 200 chunks (sanity check for CHUNK_SIZE=512)
- Zero chunks have empty `content` field

## Failure modes
- When OpenAI API is unavailable, the document status is `failed` (not `indexed`), and retrying the upload succeeds after the API recovers
- When pypdf raises an exception on a corrupted page, the pipeline continues with remaining pages and logs the error

# Eval Design

**Golden set:** 3 sample files in `scripts/` (sample_oom.log, sample_network.log, sample_runbook.md)

**Measurement:**
```bash
uv run python scripts/seed_data.py
# Then verify:
mongosh faultatlas --eval "
  print('Total chunks:', db.chunks.countDocuments());
  print('Chunks with embedding:', db.chunks.countDocuments({embedding: {\$exists: true}}));
  print('Chunks with empty content:', db.chunks.countDocuments({content: ''}));
"
# Expected: chunks_with_embedding == total_chunks, empty_content == 0
```

**Threshold:** all 3 sample files indexed with 0 empty chunks and embedding coverage = 100%

# Model / Data Dependencies

- Embedding model: `text-embedding-3-small` (OpenAI) — changing this requires re-ingesting all documents
- `CHUNK_SIZE=512`, `CHUNK_OVERLAP=64` — changing these invalidates existing chunks
- No LLM involved in Phase 1 ingestion — purely deterministic pipeline

# Out of Scope

- AI-adaptive chunking / semantic boundary detection (Phase 2+)
- OCR for scanned documents (Phase 2+)
- Binary file storage / object store (Phase 2+)
- Kafka async pipeline (Phase 2)
- Metadata auto-generation (tags, summaries) (Phase 2+)

# Notes for CodeX Review

- Verify idempotency: is the Redis key set BEFORE or AFTER MongoDB insert? (should be after successful insert to avoid orphaned idempotency keys)
- Verify error propagation: does a mid-batch embedding failure correctly mark the document as `failed` rather than leaving it in `embedding` status permanently?
- Check `source_metadata.unreadable_pages` is populated for partial PDF failures
- Unit test: does `chunk_text("short text")` return exactly one chunk with no truncation?
