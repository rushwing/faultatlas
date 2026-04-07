---
req_id: REQ-000
title: Story title
status: draft          # draft | ready | in_progress | review | done | cancelled
phase: phase-1         # phase-1 | phase-2 | phase-3
milestone: M1.x        # M1.1 … M3.x
priority: P0           # P0 critical | P1 high | P2 nice-to-have
depends_on: []         # [REQ-001, REQ-002]
owner: danielwong
---

# User Story

As [role], when [situation], I want [capability] so that [outcome].

# Goal

One paragraph. What problem does this solve in the context of FaultAtlas? Why now?

# AI Behavior Definition

## Capability
What the AI system perceives, decides, and generates in this feature.
- **Perceive:** what inputs does the AI receive?
- **Decide/Generate:** what reasoning or output does it produce?
- **Interaction paradigm:** how does the result surface to the user? (API response / stream / async callback)

## Boundary
What the AI must NOT do in this feature.
- Must not ... (hallucinate when evidence is absent — return low confidence instead)
- Must not ... (silently drop context — log and flag instead)
- Must not ... (exceed token budget — truncate deterministically)

## Fallback / Degradation
What happens when the AI cannot perform the primary behavior?
- Condition X → fallback behavior Y
- Always prefer a flagged partial result over a silent failure

# Deliverables

- [ ] API endpoint: `METHOD /path` — request/response schema
- [ ] Service / module: what code is added or changed
- [ ] Data: what MongoDB documents or Redis keys are created/updated
- [ ] Tests: unit + integration coverage

# API Contract (key endpoints)

```
POST /example
Request:  { field: type }
Response: { field: type }
Errors:   4xx conditions
```

# Acceptance Criteria

## Functional
1. Given [precondition], when [action], then [result].

## Performance / Quality
- Metric: [target] measured by [method]
- Latency: p95 < X ms under Y concurrent requests

## Failure modes
- When [bad input], the system [specific behavior], not [unacceptable behavior].

# Eval Design

How do we know this is working? Define the smallest verifiable test set.
- **Golden set:** N examples with known-correct outputs
- **Measurement:** script / query / command that produces a pass/fail number
- **Threshold:** what score is "good enough" to merge?

> If no eval is defined, the AC metrics are unverifiable. Do not mark this story done without one.

# Model / Data Dependencies

- Embedding model: (e.g. `text-embedding-3-small` — changing this invalidates stored vectors)
- LLM: (e.g. `Qwen2.5-7B-Instruct` via SGLang — prompt template tied to this model's instruction format)
- Prompt template version: (e.g. `prompts.py::SYSTEM_PROMPT` Layer 1)
- Required seed data: (e.g. at least 3 documents indexed before this can be tested)

# Out of Scope

- Feature X (Phase 2)
- Feature Y (not needed for benchmark proof)

# Notes for CodeX Review

What should the reviewer focus on? (schema correctness, edge cases, eval coverage, prompt safety)
