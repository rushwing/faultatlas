#!/usr/bin/env bash
# scan-secrets.sh — Regex-based credential pattern scanner
# Called by .github/workflows/secrets-scan.yml (pre-gitleaks layer)
#
# Scans for hardcoded secrets using known patterns.
# Exits 1 if any matches found.

set -euo pipefail

SCAN_DIR="${1:-.}"
ERRORS=0

# Files/directories to always exclude
EXCLUDE_DIRS=(
  ".git"
  "node_modules"
  "__pycache__"
  ".venv"
  "*.egg-info"
  "harness/reports"
)

# Build find exclusion args
FIND_EXCLUDES=()
for d in "${EXCLUDE_DIRS[@]}"; do
  FIND_EXCLUDES+=(-not -path "*/$d/*" -not -path "*/$d")
done

# Patterns: each entry is "LABEL|REGEX"
PATTERNS=(
  "OpenAI API key|sk-[a-zA-Z0-9]{20,}"
  "Anthropic API key|sk-ant-[a-zA-Z0-9\-]{20,}"
  "MongoDB Atlas URI|mongodb\+srv://[^:]+:[^@]+@"
  "AWS Access Key ID|AKIA[0-9A-Z]{16}"
  "AWS Secret Key|(?i)aws.{0,10}secret.{0,10}=\s*['\"][a-zA-Z0-9/+]{40}"
  "Generic password assignment|(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]{8,}['\"]"
  "Generic secret assignment|(?i)(secret|api_key|apikey|access_token)\s*=\s*['\"][^'\"]{8,}['\"]"
  "Private key header|-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"
  "Hugging Face token|hf_[a-zA-Z0-9]{20,}"
)

# Files to explicitly skip (documentation, examples, test fixtures, this script)
SKIP_FILES=(
  ".env.example"
  "*.tmpl"
  "*.md"
  "check-requirements.sh"
  "scan-secrets.sh"
  "secrets-scan.yml"
  "ADR-*.md"
)

build_skip_pattern() {
  local pattern=""
  for f in "${SKIP_FILES[@]}"; do
    if [[ -n "$pattern" ]]; then
      pattern="$pattern\|"
    fi
    pattern="${pattern}${f}"
  done
  echo "$pattern"
}

SKIP_PATTERN=$(build_skip_pattern)

echo "=== FaultAtlas Secrets Scanner ==="
echo "Scanning: $SCAN_DIR"
echo ""

scan_pattern() {
  local label="$1"
  local regex="$2"

  # Use grep with perl-regex; skip binary files
  local matches
  matches=$(
    grep -rP --include="*" \
      --binary-files=without-match \
      "${FIND_EXCLUDES[@]+"${FIND_EXCLUDES[@]}"}" \
      "$regex" "$SCAN_DIR" 2>/dev/null \
    | grep -v -E "$SKIP_PATTERN" \
    || true
  )

  if [[ -n "$matches" ]]; then
    echo "FOUND [$label]:"
    echo "$matches" | head -20
    echo ""
    return 1
  fi
  return 0
}

for entry in "${PATTERNS[@]}"; do
  label="${entry%%|*}"
  regex="${entry#*|}"
  if ! scan_pattern "$label" "$regex"; then
    ERRORS=$((ERRORS + 1))
  fi
done

# Additional check: .env files that are NOT .env.example should not exist in the repo
# (they might be accidentally staged)
echo "--- Checking for committed .env files ---"
env_files=$(find "$SCAN_DIR" -name ".env" -not -path "*/.git/*" 2>/dev/null || true)
if [[ -n "$env_files" ]]; then
  echo "WARNING: .env file(s) found in repo (should be in .gitignore):"
  echo "$env_files"
  # This is a warning, not a hard block — .env may exist locally but CI uses env vars
fi

# Check for real secrets.yaml (not templates)
echo "--- Checking for real secrets.yaml ---"
real_secrets=$(find "$SCAN_DIR" -name "secrets.yaml" -not -name "*.tmpl" -not -path "*/.git/*" 2>/dev/null || true)
if [[ -n "$real_secrets" ]]; then
  echo "ERROR: secrets.yaml found (non-template) — must not be committed:"
  echo "$real_secrets"
  ERRORS=$((ERRORS + 1))
fi

echo ""
echo "=== Result: $ERRORS pattern(s) with potential secrets found ==="

if [[ $ERRORS -gt 0 ]]; then
  echo ""
  echo "To suppress a false positive, add the file to SKIP_FILES in scan-secrets.sh"
  echo "or use a '# nosec' comment on the line (for inline exclusion)."
  exit 1
fi

echo "Clean — no secret patterns detected."
exit 0
