#!/usr/bin/env bash
# End-to-end smoke test using curl
set -euo pipefail

BASE=${API_BASE:-"http://localhost:8000"}
KEY=${API_KEY:-"changeme-local-dev"}
H="X-API-Key: $KEY"

echo "=== FaultAtlas Smoke Test ==="

echo -n "[1] Health check... "
curl -sf "$BASE/health" | grep -q '"ok"' && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "[2] Readiness check... "
curl -sf "$BASE/ready" -H "$H" | grep -q '"ok"' && echo "PASS" || { echo "FAIL"; exit 1; }

TMP_DOC=$(mktemp)
# Include a unique run ID so repeated smoke test runs don't hit the 409 idempotency check
cat > "$TMP_DOC" <<EOF
2024-01-15T02:13:44Z WARN  kernel: Out of memory: Kill process 1234 (java) score 900
2024-01-15T02:13:44Z ERROR java.lang.OutOfMemoryError: Java heap space
2024-01-15T02:13:44Z FATAL payment-processor crashed. Restarting in 5s.
smoke-test-run-id: $(date +%s)-$$
EOF

echo -n "[3] Upload document... "
UPLOAD_JSON=$(curl -sf -X POST "$BASE/documents" \
  -H "$H" \
  -F "file=@${TMP_DOC};type=text/plain")
DOC_ID=$(printf '%s' "$UPLOAD_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")
STATUS=$(printf '%s' "$UPLOAD_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
[[ "$STATUS" == "indexed" ]] && echo "PASS (id=$DOC_ID)" || { echo "FAIL"; exit 1; }

echo -n "[4] Check document status... "
STATUS=$(curl -sf "$BASE/documents/$DOC_ID/status" -H "$H" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
[[ "$STATUS" == "indexed" ]] && echo "PASS (status=$STATUS)" || { echo "FAIL"; exit 1; }

echo -n "[5] Diagnose... "
DIAG_JSON=$(curl -sf -X POST "$BASE/diagnose" \
  -H "$H" -H "Content-Type: application/json" \
  -d '{"query":"Why is payment-processor failing with Java heap space errors?"}')
SUMMARY=$(printf '%s' "$DIAG_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['summary'])")
[[ -n "$SUMMARY" ]] && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "[6] Prompt debug... "
LAYER1_HASH=$(curl -sf "$BASE/debug/prompt?query=Why%20is%20payment-processor%20failing%20with%20Java%20heap%20space%20errors%3F" -H "$H" | python3 -c "import sys,json; print(json.load(sys.stdin)['layer1_hash'])")
[[ -n "$LAYER1_HASH" ]] && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "[7] Benchmark... "
BENCH_JSON=$(curl -sf -X POST "$BASE/benchmark/run" \
  -H "$H" -H "Content-Type: application/json" \
  -d '{"runs_per_condition":1,"backend":"sglang"}')
RUN_ID=$(printf '%s' "$BENCH_JSON" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
[[ -n "$RUN_ID" ]] && echo "PASS (run_id=$RUN_ID)" || { echo "FAIL"; exit 1; }

echo ""
echo "All checks passed."
rm -f "$TMP_DOC"
