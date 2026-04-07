---
req_id: REQ-015
title: Production secrets management
status: draft
phase: phase-3
milestone: M3.3
priority: P0
depends_on: [REQ-011]
owner: danielwong
---

# User Story

As a DevOps engineer preparing FaultAtlas for a customer pilot, I want secrets (OpenAI API key, MongoDB URI, service API keys) to be managed outside of the repository and injected at deploy time via an industry-standard secrets operator, so that no credentials are ever stored in Git, even accidentally.

# Goal

Replace the `secrets.yaml.tmpl` stub with a working Sealed Secrets or external-secrets-operator integration. This is a P0 for Phase 3 because committing real secrets to Git — even in a private repo — is an unacceptable risk in a customer-facing deployment.

# AI Behavior Definition

No AI behavior — secrets infrastructure.

## Boundary
- Must NOT store any secret value in any file committed to Git — not even base64-encoded
- Must NOT log secret values — only log key names (e.g., `"OPENAI_API_KEY is set"`, never its value)

# Deliverables

- [ ] `infra/k8s/secrets/` — replace `.yaml.tmpl` with `ExternalSecret` or `SealedSecret` resources
- [ ] `docs/runbooks/secrets-rotation.md` — procedure for rotating each secret type
- [ ] `scripts/deploy/seal_secrets.sh` — helper script to seal secrets locally before committing
- [ ] CI check: `grep -r "sk-" infra/ docs/` fails the pipeline if an OpenAI key pattern is found

# Acceptance Criteria

1. No file in the repository contains a value matching `sk-[a-zA-Z0-9]{32,}` (OpenAI key pattern)
2. `helm install` on a cluster with external-secrets-operator deploys successfully with secrets injected from the secrets backend
3. Rotating the OpenAI API key requires only updating the secrets backend, not redeploying the application

# Eval Design

```bash
# CI leak detection
grep -rE "sk-[a-zA-Z0-9]{32,}" . --exclude-dir=.git
# Must return no matches

# Verify secrets injection
kubectl get secret faultatlas-secrets -n faultatlas -o json | \
  python3 -c "import sys,json,base64; d=json.load(sys.stdin); print(base64.b64decode(d['data']['OPENAI_API_KEY']).decode()[:4])"
# Should print "sk-" (confirms secret is present but we only check prefix)
```

# Model / Data Dependencies

- Requires either: Sealed Secrets controller or external-secrets-operator installed in target cluster
- Secrets backend: Kubernetes native secrets (for demo), or AWS Secrets Manager / Vault (for production)

# Out of Scope

- Hardware Security Module (HSM) integration
- Secret versioning and automatic rotation triggers
- Vault dynamic secrets

# Notes for CodeX Review

- Verify the CI grep pattern covers all known secret formats (OpenAI, Anthropic, MongoDB Atlas connection string patterns)
- Check: does the `seal_secrets.sh` script refuse to run if the sealed-secrets certificate is older than 30 days?
