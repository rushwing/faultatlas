# ADR-003 — Commercial Evolution Path

| Field | Value |
|---|---|
| **Status** | Draft — for review |
| **Date** | 2026-04-07 |
| **Deciders** | danielwong |

> This ADR documents the intended evolution from MVP demo to a commercially viable product. It is written at MVP stage deliberately — to ensure architectural decisions made now do not close off important commercial paths later. It is a living document and should be updated as the market understanding evolves.

---

## Context

FaultAtlas Phase 1 is a technical proof-of-concept: a single-engineer, single-GPU deployment that validates the SGLang prefix caching hypothesis in an incident RAG context. It is not a product.

The path from this MVP to a commercial product requires answering three distinct questions:

1. **Who pays, and for what?** (Go-to-market)
2. **What architecture changes are required at scale?** (Technical roadmap)
3. **What is the defensible moat?** (Product strategy)

This ADR attempts to map the answers, so that MVP engineering decisions can be made with commercial constraints in mind.

---

## Target Customer Segments

### Segment A — Enterprise SRE / NOC teams (primary)

**Problem:** Large-scale infrastructure generates millions of log lines per day. On-call engineers spend 40–60% of incident response time correlating logs, runbooks, and historical cases manually. Existing tools (PagerDuty, Grafana, Splunk) surface alerts but do not explain them.

**What they buy:** A copilot that reduces Mean Time to Diagnose (MTTD) by surfacing relevant runbook sections, similar past incidents, and structured root-cause hypotheses — without sending sensitive log data to an external API.

**Key constraint:** Data sovereignty. Large enterprises (finance, telecom, healthcare) cannot send internal log data to OpenAI. Local deployment is a requirement, not a preference.

**Relevance to MVP:** The MVP's local SGLang deployment addresses this constraint directly. The "LLM_BACKEND switchable" design means the same codebase works for both cloud API (evaluation) and local model (production).

### Segment B — Platform/DevOps tooling vendors (secondary)

**Problem:** AIOps platform vendors (Dynatrace, Moogsoft, OpsRamp) have strong monitoring but weak diagnostic reasoning. They want to embed structured LLM diagnosis into their products without building model serving infrastructure.

**What they buy:** An SDK or hosted API for structured incident diagnosis, with SLA guarantees.

**Relevance to MVP:** The fixed DiagnosisResponse JSON schema and the OpenAI-compatible interface design means FaultAtlas can be embedded as a service. The schema stability constraint (from ADR-001) is commercially valuable — SDK consumers need schema versioning.

### Segment C — Managed service providers (MSP) / MSSPs (tertiary)

**Problem:** MSPs manage hundreds of customer environments and cannot scale human analysts. They need tools that can diagnose incidents across heterogeneous environments with minimal per-customer customization.

**What they buy:** Multi-tenant SaaS with per-customer knowledge base isolation and audit trails.

**Relevance to MVP:** The audit_log collection and the per-document metadata design support multi-tenancy when combined with an auth layer (Phase 3). The Redis key namespacing by user_id is already designed for this.

---

## Commercial Architecture Requirements

The following architectural capabilities are required for each commercial segment. MVP phase coverage is noted.

| Capability | Segment A | Segment B | Segment C | MVP phase | Notes |
|---|---|---|---|---|---|
| Local LLM deployment | Required | Optional | Optional | Phase 1 | Core MVP |
| OpenAI API fallback | Nice to have | Required | Optional | Phase 1 | Implemented |
| Fixed JSON output schema | Required | Required | Required | Phase 1 | DiagnosisResponse |
| Data sovereignty (on-prem) | Required | Optional | Required | Phase 1 | Local deploy |
| Schema versioning / stability | Required | Required | Required | Phase 2 | Prompt version tracking |
| Streaming responses | Preferred | Required | Preferred | Phase 2 | SSE |
| Async ingestion pipeline | Required | Required | Required | Phase 2 | Kafka activation |
| Multi-tenant isolation | Not needed | Not needed | Required | Phase 3 | Namespace per customer |
| JWT auth / RBAC | Required | Required | Required | Phase 3 | API key stub in Phase 1 |
| Audit trail | Required | Required | Required | Phase 1 | audit_log collection |
| Usage metrics / billing hooks | Not needed | Required | Required | Phase 3 | |
| SLA / uptime guarantees | Required | Required | Required | Phase 3+ | Requires HA deployment |
| Custom model fine-tuning | Preferred | Optional | Optional | Post-Phase 3 | |
| Real-time log streaming (Kafka ingest) | Required | Optional | Required | Phase 2 | |

---

## Defensible Moat — Three Layers

### Layer 1 — Prompt architecture expertise (near-term moat, 6–18 months)

The 3-layer prompt structure (fixed system prefix → deterministic context scaffold → variable user query) is not obvious. Most RAG implementations inject dynamic content into the system prompt or shuffle context order, which fragments prefix caching and negates the TTFT advantage.

**Moat:** Deep understanding of how SGLang RadixAttention works at the token level, and how to structure prompts to maximally exploit it. This is documented in our ADRs and is the subject of the benchmark.

**Risk:** This knowledge becomes commoditized as SGLang usage grows and best practices are published. The moat is 6–18 months.

**Defense:** Move faster — publish a paper or technical blog post to establish thought leadership before others do.

### Layer 2 — Domain-specific knowledge base tooling (medium-term moat, 18–36 months)

The value of FaultAtlas increases non-linearly with the quality and size of the knowledge base. An enterprise that has indexed 5 years of runbooks, post-mortems, and incident cases into FaultAtlas has a system that is significantly more useful than a fresh install.

**Moat:** Data flywheel. The longer a customer uses the system, the more historical cases are indexed, the better the retrieval quality, the more accurate the diagnoses.

**Defense:**
- Make ingestion frictionless (Kafka, CI/CD integration, log collector plugins)
- Make citations auditable (customers can see exactly which runbook section informed a diagnosis)
- Make feedback loops easy (thumbs-up/down on diagnoses feeds back into retrieval ranking)

### Layer 3 — Infrastructure-aware structured output (long-term moat, 36+ months)

General-purpose LLMs generate free-form text. FaultAtlas generates structured output calibrated to specific infrastructure topologies: "suspected_causes" is not a generic list — it is ranked by observed evidence weight, filtered by the customer's actual service graph.

**Moat:** Domain-specific output schema evolution. Over time, the DiagnosisResponse schema can incorporate topology-aware fields (affected services, blast radius, dependency chain), making FaultAtlas outputs directly actionable in incident management tools (PagerDuty, Jira Service Management).

**Defense:** Build integrations early. A FaultAtlas diagnosis that auto-creates a Jira ticket with pre-populated fields is stickier than one that just returns JSON.

---

## Go-to-Market Sequence

### Stage 1 — Technical validation (current, Phase 1)

- **Goal:** Prove the performance hypothesis. Produce a shareable benchmark report.
- **Audience:** Engineering peers, open-source community, potential technical co-founders
- **Output:** Published benchmark results, open-source MVP, technical blog post

### Stage 2 — Design partner (Phase 2)

- **Goal:** Find 2–3 enterprise SRE teams willing to run FaultAtlas on their actual knowledge base and measure MTTD improvement
- **Audience:** SRE leads at mid-to-large tech companies with on-prem requirements
- **Requirements:** Async ingestion (Phase 2), streaming responses (Phase 2), basic auth (Phase 3)
- **Metric:** Customer reports measurable reduction in time-to-diagnose for incidents where FaultAtlas was used vs. not used

### Stage 3 — Pilot → Paid (Phase 3 / commercial)

- **Goal:** Convert design partner to paying customer; establish pricing model
- **Pricing options:**
  - Seat-based (per concurrent engineer)
  - Consumption-based (per diagnosis request)
  - Platform fee (per GB of indexed knowledge base)
- **Requirements:** JWT auth, audit log export, SLA, multi-tenant if MSP

### Stage 4 — Scale (post-Phase 3)

- Managed cloud offering (no self-hosted requirement)
- Multi-cloud, multi-region
- ISV partnerships (embed in AIOps platforms)
- Fine-tuning service (customer data stays on-prem; fine-tuned model weights returned)

---

## Technical Debt That Must Be Resolved Before Commercial

The following decisions made for MVP speed **will** cause problems at commercial scale and should be scheduled for resolution.

| Debt item | Created by | Impact if not resolved | Target resolution |
|---|---|---|---|
| In-memory cosine similarity (no vector index) | ADR-002 (Phase 1) | Retrieval latency degrades >10k chunks | Phase 2 — Atlas Vector Search |
| OpenAI embedding API dependency | ADR-002 (Phase 1) | Data sovereignty blocked for Segment A customers | Phase 2 — local embedding model (BGE-M3) |
| Single API key auth | ADR-002 Phase 1 | Cannot support multi-user or multi-team | Phase 3 — JWT + RBAC |
| DiagnosisResponse schema v0 (no versioning) | Phase 1 | Breaking changes affect all SDK consumers | Phase 2 — version field + migration |
| No prompt version tracking | Phase 1 | Cannot A/B test prompt changes or track cache hit degradation | Phase 2 — `prompt_version` field on sessions |
| MongoDB used for embeddings (not vector-native) | ADR-002 | Cannot do approximate nearest-neighbor at scale | Phase 2 |
| No feedback signal from diagnosis | Phase 1 | No data flywheel; knowledge base quality stagnant | Phase 2 — thumbs up/down endpoint |

---

## What FaultAtlas Is Not

To avoid building the wrong thing, it is useful to define what FaultAtlas explicitly is **not** — and why these are the right exclusions.

| Non-goal | Why it's excluded |
|---|---|
| **A general-purpose chatbot** | The fixed output schema and retrieval-grounded generation are load-bearing; removing them to make it "more conversational" would destroy the citation and auditability properties that enterprise customers require |
| **An automated remediation engine** | Executing remediation actions (restarting services, scaling deployments) changes the risk profile from "advisory tool" to "autonomous agent." This requires change management integration, approval workflows, and a completely different liability model |
| **A log aggregation platform** | We are not competing with Splunk, Datadog, or Elastic. We integrate with them (ingesting from their export APIs) but do not replace them |
| **A real-time monitoring system** | Alerting and anomaly detection are solved problems. We start where the alert fires and ends — diagnosis |
| **A fine-tuning service for general models** | Fine-tuning on customer data has enormous data governance complexity. If we do fine-tuning, it is narrow (incident classification, not general instruction following) and always on-prem |

---

## Decision

Accept this ADR as a living document that guides:

1. Which MVP architectural decisions should be treated as permanent (DiagnosisResponse schema, 3-layer prompt structure, local deployment capability)
2. Which MVP shortcuts must be paid back before commercial launch (auth, vector index, schema versioning)
3. Which commercial features are never added to the core MVP (remediation, fine-tuning service, log aggregation)

This document should be reviewed and updated at the start of each development phase.
