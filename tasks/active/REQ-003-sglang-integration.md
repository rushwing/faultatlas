---
req_id: REQ-003
title: SGLang model server integration
status: draft
phase: phase-1
milestone: M1.3
priority: P0
depends_on: []
owner: danielwong
---

# User Story

As a developer deploying FaultAtlas on AutoDL, I want the application to call either a local SGLang server (Qwen2.5-7B-Instruct on RTX 4090) or the OpenAI API through the same interface, switchable via a single environment variable, so that I can develop and test without GPU hardware and deploy with GPU hardware without changing any application code.

# Goal

Create the LLM client abstraction that powers both the diagnosis endpoint and the benchmark pipeline. The switching mechanism (`LLM_BACKEND`) is load-bearing for the project: it enables development on any machine (OpenAI API) and performance validation on AutoDL (SGLang). Getting this interface wrong means every prompt change requires testing on two backends separately.

# AI Behavior Definition

## Capability
- **Perceive:** a fully-assembled prompt (system + context + user query), generation parameters (max_tokens, temperature)
- **Decide:** route the call to the correct backend based on `LLM_BACKEND` env var; capture TTFT and total latency; extract `prefix_cache_hint` from SGLang response headers if available
- **Generate:** chat completion response, parsed into `content` string + usage metadata
- **Interaction paradigm:** async function call from orchestrator — not an HTTP endpoint itself

## Boundary
- Must NOT hardcode model names, API keys, or base URLs in application logic — all come from `Settings`
- Must NOT swallow SGLang errors — surface them as structured exceptions so the diagnosis endpoint can return a meaningful HTTP error
- Must NOT change the prompt content based on which backend is active — the same prompt goes to both backends; this is critical for benchmark comparability
- Must NOT retry on SGLang OOM errors (`CUDA out of memory`) — fail fast and surface the error; retrying will not help

## Fallback / Degradation
- SGLang server unreachable → raise `LLMBackendUnavailableError` with `backend: "sglang"`, caught by diagnosis endpoint → HTTP 503
- OpenAI API rate limit → retry with exponential backoff (max 3), then raise `LLMBackendUnavailableError`
- Response content is empty string → raise `LLMEmptyResponseError` — do not return an empty diagnosis

# Deliverables

- [ ] `services/api/app/llm/client.py` — `LLMClient` with `complete()` async method
- [ ] `services/api/app/llm/backends/sglang.py` — SGLang OpenAI-compat HTTP client
- [ ] `services/api/app/llm/backends/openai.py` — OpenAI SDK client
- [ ] `services/api/app/llm/metrics.py` — TTFT capture, latency measurement, prefix cache hint extraction
- [ ] `services/api/app/llm/__init__.py` — factory: `get_llm_client(settings) → LLMClient`
- [ ] Unit tests: backend routing, error propagation, TTFT measurement
- [ ] Integration test (SGLang backend): requires running SGLang server, marked `@pytest.mark.requires_gpu`

# API Contract (internal)

```python
# services/api/app/llm/client.py

class LLMResponse:
    content: str
    tokens_used: int
    ttft_ms: int           # time to first token (ms)
    total_latency_ms: int
    prefix_cache_hint: str  # "cold" | "shared" | "no_shared" | "unknown"

class LLMClient:
    async def complete(
        self,
        messages: list[dict],         # [{"role": ..., "content": ...}]
        max_tokens: int = 1024,
        temperature: float = 0.1,
    ) -> LLMResponse: ...
```

TTFT measurement: record `time.monotonic()` before the request; for non-streaming calls, approximate TTFT as `total_latency × (1 / output_tokens)` — streaming TTFT is a Phase 2 improvement (REQ-007).

`prefix_cache_hint` source:
- SGLang: extract from response header `x-prefix-cache-hit` if present (SGLang ≥ 0.3 exposes this); otherwise `"unknown"`
- OpenAI: always `"unknown"` (no prefix cache visibility)

# Acceptance Criteria

## Functional
1. With `LLM_BACKEND=openai` and valid `OPENAI_API_KEY`, `LLMClient.complete()` returns a non-empty `LLMResponse`
2. With `LLM_BACKEND=sglang` and SGLang server running, same call returns `LLMResponse` with `ttft_ms > 0`
3. Setting `LLM_BACKEND=sglang` with SGLang server down raises `LLMBackendUnavailableError`, not an unhandled exception
4. The exact same messages list produces the exact same prompt text regardless of which backend is active

## Performance / Quality
- `LLMClient` overhead (excluding actual LLM call) < 5ms
- TTFT measurement error < 10ms (verified by comparing to streaming TTFT in Phase 2)

## Failure modes
- When SGLang returns `CUDA out of memory`, the error is not retried and surfaces within 2s
- When `LLM_BACKEND` is set to an unknown value, startup fails with a clear config error, not a runtime exception at call time

# Eval Design

**Measurement:**
```bash
# Test 1: backend routing
LLM_BACKEND=openai uv run pytest services/api/tests/unit/test_llm_client.py -v

# Test 2: SGLang integration (requires GPU)
LLM_BACKEND=sglang uv run pytest services/api/tests/integration/test_llm_sglang.py \
  -m requires_gpu -v
```

**Threshold:** all unit tests pass; SGLang integration test returns `ttft_ms > 0` and `content` non-empty

# Model / Data Dependencies

- SGLang server: `Qwen/Qwen2.5-7B-Instruct` or `Qwen/Qwen3-8B`, must be running before integration tests
- OpenAI model: `gpt-4o-mini` (configurable via `OPENAI_CHAT_MODEL`)
- Prompt format: Qwen instruction format (`<|im_start|>system\n...<|im_end|>`) is handled by SGLang's chat template — do not apply it manually in `LLMClient`

# Out of Scope

- Streaming token delivery (Phase 2 — REQ-007)
- Model selection per request (Phase 3)
- Local embedding model via SGLang (Phase 2)

# Notes for CodeX Review

- **Critical:** verify that `LLMClient` does NOT modify `messages` content — the benchmark validity depends on identical prompts going to both backends
- Check: is `LLMBackendUnavailableError` a subclass of a base `FaultAtlasError`? Error hierarchy should be consistent
- Check: does `prefix_cache_hint` gracefully default to `"unknown"` when the SGLang header is absent (older SGLang versions)?
- Verify: does startup-time validation of `LLM_BACKEND` happen in `config.py` (`@validator`) rather than lazily at call time?
