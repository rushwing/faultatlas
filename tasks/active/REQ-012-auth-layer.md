---
req_id: REQ-012
title: Authentication layer (JWT + RBAC)
status: draft
phase: phase-3
milestone: M3.6
priority: P1
depends_on: []
owner: danielwong
---

# User Story

As a platform administrator onboarding a first external user or team, I want each API consumer to have their own API key (or JWT) with per-key rate limiting, so that different users and services can be identified in audit logs, revoked independently, and rate-limited without affecting each other.

# Goal

Replace the single shared `API_KEY` with a proper multi-key authentication system. This is the minimum viable auth layer for a customer pilot or partner integration. Full RBAC (roles, permissions) is out of scope for this story.

# AI Behavior Definition

No AI behavior — authentication infrastructure.

## Boundary
- Must NOT break existing single-key behavior during transition — support both the legacy `API_KEY` (as a "super key") and new per-user keys
- Must NOT log full API keys anywhere — log only the key ID prefix (first 8 chars)

# Deliverables

- [ ] MongoDB `api_keys` collection: `{ key_id, key_hash, user_id, name, created_at, revoked_at? }`
- [ ] `POST /admin/keys` — create API key (returns key once, stores hash)
- [ ] `DELETE /admin/keys/{key_id}` — revoke key
- [ ] FastAPI dependency: `verify_api_key()` checks key hash against MongoDB
- [ ] Redis rate limiting: `api:ratelimit:{key_id}:{minute_bucket}` → count (already designed in `RedisKeys`)
- [ ] `user_id` from auth context propagated to all audit log entries and session records
- [ ] Unit tests: key creation, revocation, rate limit enforcement

# Acceptance Criteria

1. `POST /admin/keys` returns a new key; subsequent `POST /diagnose` with that key succeeds
2. `DELETE /admin/keys/{key_id}` revokes the key; subsequent calls with that key return 401
3. After 100 requests in 60s, the 101st request returns 429 (rate limit)
4. Audit log entries include `key_id` and `user_id` for every diagnosis call

# Eval Design

```bash
# Create key
KEY=$(curl -s -X POST http://localhost:8000/admin/keys \
  -H "X-API-Key: $ADMIN_KEY" -d '{"name":"test-user"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])")
# Use key
curl -s http://localhost:8000/health -H "X-API-Key: $KEY"
# Revoke key
curl -s -X DELETE http://localhost:8000/admin/keys/{key_id} -H "X-API-Key: $ADMIN_KEY"
# Verify revoked
curl -s http://localhost:8000/health -H "X-API-Key: $KEY"  # should return 401
```

# Model / Data Dependencies

- No LLM dependencies
- `RedisKeys.rate_limit()` already designed — just needs activation

# Out of Scope

- JWT / OAuth2 flows (design partner request triggers this)
- Role-based permissions (admin vs. reader)
- SSO integration

# Notes for CodeX Review

- Verify key hashing uses bcrypt or Argon2, not plain SHA-256 (timing attack resistance)
- Check: is the admin key protected from rate limiting? (it should be exempt)
