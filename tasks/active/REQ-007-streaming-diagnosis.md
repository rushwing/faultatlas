---
req_id: REQ-007
title: Streaming diagnosis responses (SSE)
status: draft
phase: phase-2
milestone: M2.2
priority: P1
depends_on: [REQ-004]
owner: danielwong
---

# User Story

As an on-call engineer using FaultAtlas during a live incident, I want to see the diagnosis tokens arriving in real time rather than waiting for the full response, so the interaction feels responsive and I can start acting on early parts of the answer while the rest generates.

# Goal

Add Server-Sent Events (SSE) streaming to `POST /diagnose`. This also improves TTFT measurement accuracy — in Phase 1, TTFT is approximated from total latency; streaming gives true first-token measurement.

# AI Behavior Definition

## Capability
- Same retrieval + prompt build as REQ-004
- **New:** stream token chunks via SSE; send a final `[DONE]` event with metadata (tokens_used, latency, prefix_cache_hint)

## Boundary
- Must NOT start streaming before retrieval completes — the complete context must be assembled before the LLM call starts
- Must NOT stream partial JSON — the structured `DiagnosisResponse` is sent as the final event, not streamed token-by-token

## Fallback / Degradation
- Client disconnects mid-stream → LLM generation is cancelled (httpx streaming is closed), session marked `interrupted`
- Streaming not supported by backend → fall back to non-streaming, return full response

# Deliverables

- [ ] `POST /diagnose?stream=true` SSE response
- [ ] `services/api/app/llm/backends/sglang.py` — streaming support
- [ ] True TTFT measurement (first token arrival time)
- [ ] Update `DiagnosisResponse` with accurate `ttft_ms` from streaming

# Acceptance Criteria

1. `POST /diagnose?stream=true` returns `Content-Type: text/event-stream`
2. First SSE event arrives within 2s on SGLang (RTX 4090, warm cache)
3. Final event contains complete `DiagnosisResponse` JSON
4. True TTFT (first token) < approximated TTFT from Phase 1 (confirms Phase 1 approximation was conservative)

# Eval Design

```bash
curl -N -X POST "http://localhost:8000/diagnose?stream=true" \
  -H "X-API-Key: ..." -H "Content-Type: application/json" \
  -d '{"query": "OOM in payment service"}' | head -5
# First event should arrive within 2s
```

# Model / Data Dependencies

- SGLang streaming: `stream=True` in OpenAI client call
- True TTFT replaces Phase 1 approximation in benchmark reports

# Out of Scope

- WebSocket bidirectional streaming
- Per-token structured output streaming

# Notes for CodeX Review

- Verify SSE heartbeat is sent if no tokens arrive within 5s (prevents proxy timeouts)
- Check: does the final `[DONE]` event include `prefix_cache_hint`?
