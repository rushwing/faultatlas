#!/usr/bin/env bash
# End-to-end smoke test using curl
set -euo pipefail

BASE=${API_BASE:-"http://localhost:8000"}
KEY=${API_KEY:-"changeme-local-dev"}
H="X-API-Key: $KEY"

echo "=== FaultAtlas Smoke Test ==="

echo -n "[1] Health check... "
curl -sf "$BASE/health" | grep -q '"ok"' && echo "PASS" || { echo "FAIL"; exit 1; }

echo -n "[2] Upload document... "
DOC_ID=$(curl -sf -X POST "$BASE/documents" \
  -H "$H" \
  -F "file=@scripts/sample_oom.log;type=text/plain" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['document_id'])")
echo "PASS (id=$DOC_ID)"

echo -n "[3] Check document status... "
STATUS=$(curl -sf "$BASE/documents/$DOC_ID/status" -H "$H" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
echo "PASS (status=$STATUS)"

echo -n "[4] Create incident... "
INC_ID=$(curl -sf -X POST "$BASE/incidents" \
  -H "$H" -H "Content-Type: application/json" \
  -d '{"title":"OOM spike on node-1","severity":"high"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "PASS (id=$INC_ID)"

echo ""
echo "All checks passed."
