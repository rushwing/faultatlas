---
req_id: REQ-011
title: Helm chart packaging
status: draft
phase: phase-3
milestone: M3.1
priority: P1
depends_on: []
owner: danielwong
---

# User Story

As a DevOps engineer deploying FaultAtlas to a cloud Kubernetes cluster, I want to install the entire stack with a single `helm install` command with environment-specific values, so that I don't have to manually apply 15 separate YAML manifests and can manage upgrades cleanly.

# Goal

Convert the `infra/k8s/` raw manifests (which are Phase 1/2 stubs) into a proper Helm chart. Enable configuration for dev, staging, and production environments via `values.yaml` variants. This is the packaging step that enables cloud deployment and customer demos on managed Kubernetes.

# AI Behavior Definition

No AI behavior — infrastructure packaging.

# Deliverables

- [ ] `infra/helm/faultatlas/` Helm chart structure
- [ ] `Chart.yaml`, `values.yaml`, `values.dev.yaml`, `values.prod.yaml`
- [ ] Templates for: Deployments, Services, ConfigMaps, Secrets (external-secrets pattern), Ingress, HPA, Jobs
- [ ] `helm lint infra/helm/faultatlas/` passes
- [ ] `helm install faultatlas ./infra/helm/faultatlas -f values.dev.yaml` deploys cleanly to a local k3s or kind cluster
- [ ] `infra/k8s/` raw manifests archived (kept for reference, not maintained)

# Acceptance Criteria

1. `helm lint` produces zero errors and zero warnings
2. `helm install` on a clean kind cluster creates all expected resources (verified by `kubectl get all -n faultatlas`)
3. `helm upgrade` with a new image tag triggers a rolling update without downtime
4. `values.prod.yaml` uses `replicaCount: 3` for api and retriever; `values.dev.yaml` uses `replicaCount: 1`

# Eval Design

```bash
kind create cluster
helm install faultatlas ./infra/helm/faultatlas -f infra/helm/faultatlas/values.dev.yaml
kubectl wait --for=condition=ready pod -l app=api -n faultatlas --timeout=120s
curl http://localhost/health  # via port-forward
```

# Model / Data Dependencies

- Requires Phase 2 Docker images to be stable (no breaking config changes)
- SGLang server is deployed separately (GPU node) — not part of the Helm chart

# Out of Scope

- Helm chart publishing to a registry
- ArgoCD / GitOps integration
- KEDA consumer lag-based autoscaling (Phase 3 stretch)

# Notes for CodeX Review

- Verify secrets are templated as external-secrets `ExternalSecret` resources, not hardcoded values
- Check: does the chart support `imagePullSecrets` for private registries?
