# ADR-001 — MVP Scope Definition

| Field | Value |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-04-07 |
| **Deciders** | danielwong |
| **Supersedes** | Initial broad-scope design (pre-2026-04-07) |

---

## Context

The original FaultAtlas design included a broad set of features: multi-agent orchestration, Kafka-driven real-time log streaming, a React frontend, RBAC, Kubernetes autoscaling, and full observability. This was appropriate for exploring the design space, but it is not appropriate for a single-engineer MVP with constrained GPU hardware (single RTX 4090 on AutoDL).

The core technical bet of FaultAtlas is that SGLang's RadixAttention-based KV prefix caching can deliver meaningfully lower TTFT on RAG workloads — enough to make local LLM serving competitive with remote API calls for repetitive incident analysis queries. This bet has not been validated.

If this bet is wrong, none of the surrounding features matter. If it is right, a focused demo of the performance advantage is more persuasive to any audience (engineering team, investor, customer) than a feature-complete but slow system.

This ADR records the decision to refocus the MVP scope onto proving that one thing.

---

## Decision

**The FaultAtlas MVP is scoped to four pipelines and one performance hypothesis.**

### The four pipelines

1. **Ingest** — Upload runbook/case/log → chunk → embed → store
2. **Retrieve** — Query → vector search → top-k evidence → prompt
3. **Diagnose** — Fixed 3-layer prompt → SGLang → structured JSON output
4. **Benchmark** — Cold vs. shared-prefix vs. no-shared-prefix TTFT/throughput comparison

Everything else is either a stub (Kafka, K8S manifests) or out of scope until a later phase.

### The performance hypothesis

> Shared-prefix repeated requests against SGLang will show ≤ 60% of the TTFT of cold-start requests, on a single RTX 4090 with Qwen2.5-7B-Instruct or Qwen3-8B.

The benchmark pipeline is the primary deliverable of Phase 1. Without it, the MVP has not been completed.

---

## Alternatives Considered

### Option A: Build full feature set, performance comes later

**Pros:** More impressive feature list; easier to show "product vision."

**Cons:** The performance proof never gets done because there is always another feature. If SGLang prefix caching does not actually produce the hypothesized gains (e.g., because our prompt structure fragments the cache, or because Qwen tokenization produces longer-than-expected shared prefixes), we would not discover this until late — after significant wasted effort.

**Rejected because:** Validates the wrong thing first. Features are cheap to add after; performance architecture is expensive to retrofit.

### Option B: Pure benchmark, no application

**Pros:** Fastest path to the performance number.

**Cons:** Not a product. Does not demonstrate the use case. Does not validate that the prompt structure (which determines cache hit rate) is realistic for actual incident analysis.

**Rejected because:** The application context — specifically the fixed 3-layer prompt structure — is what makes the prefix caching argument coherent. A pure benchmark would not test whether the architecture is useful.

### Option C: This decision (chosen)

A minimal but complete application that exercises the performance hypothesis in a realistic use case context, and measures it explicitly.

**Chosen because:** It is the smallest unit that can prove or disprove the core bet.

---

## Consequences

### Positive

- Phase 1 can be completed by one engineer in ~3 weeks
- The benchmark result is a concrete, shareable artifact (not a claim)
- The 3-layer prompt structure constraint is load-bearing and documented, preventing accidental cache fragmentation
- Stub infrastructure (Kafka, K8S) is in place — Phase 2/3 activates it, does not redesign it

### Negative

- The MVP will not be visually impressive (no frontend, no real-time streaming)
- Kafka is wired but dark in Phase 1 — engineers unfamiliar with the history may try to activate it prematurely
- The scope constraint means some reasonable requests (streaming, auth) will be explicitly deferred

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| SGLang prefix cache gains are smaller than expected | Documented in success criteria with explicit target (≤60% TTFT); if missed, this is a finding, not a failure |
| Prompt Layer 1 accidentally includes variable tokens | Prompt versioning tracks Layer 1 content; benchmark diff between versions will expose this |
| Phase 1 scope creep from "just one more feature" | This ADR is the gate. Any Phase 1 addition requires updating this ADR and MVP_SCOPE.md |

---

## References

- SGLang paper: "Efficient Memory Management for Large Language Model Serving with PagedAttention" (RadixAttention)
- SGLang GitHub: `sgl-project/sglang` — prefix caching described in README and `sglang/backend/runtime.py`
- Qwen2.5 model card: confirms compatibility with SGLang serving
- `docs/MVP_SCOPE.md` — full scope specification derived from this decision
