#!/usr/bin/env bash
# check-requirements.sh — Validate FaultAtlas REQ frontmatter and section structure
# Called by .github/workflows/requirements.yml
#
# Exit codes:
#   0 — all requirements pass
#   1 — one or more requirements have errors

set -euo pipefail

TASKS_DIR="${1:-tasks/active}"
ERRORS=0

VALID_STATUSES=("draft" "ready" "in-progress" "in-review" "done" "cancelled")
VALID_PHASES=("phase-1" "phase-2" "phase-3")
VALID_PRIORITIES=("P0" "P1" "P2")

REQUIRED_SECTIONS=(
  "# User Story"
  "# Goal"
  "# AI Behavior Definition"
  "# Deliverables"
  "# Acceptance Criteria"
  "# Eval Design"
  "# Out of Scope"
)

# Collect all known REQ IDs for depends_on validation (newline-separated string)
KNOWN_REQS_LIST=""
for f in "$TASKS_DIR"/REQ-*.md; do
  [[ -f "$f" ]] || continue
  basename_no_ext="${f##*/}"
  basename_no_ext="${basename_no_ext%.md}"
  id=$(echo "$basename_no_ext" | grep -oE '^REQ-[0-9]+')
  if [[ -n "$id" ]]; then
    KNOWN_REQS_LIST="${KNOWN_REQS_LIST}${id}"$'\n'
  fi
done

req_id_known() {
  echo "$KNOWN_REQS_LIST" | grep -qx "$1"
}

check_file() {
  local file="$1"
  local filename
  filename=$(basename "$file")
  local file_errors=0

  # Extract req_id from filename: REQ-NNN-slug.md → REQ-NNN
  local expected_id
  expected_id=$(echo "$filename" | grep -oE '^REQ-[0-9]+')
  if [[ -z "$expected_id" ]]; then
    echo "ERROR [$filename]: filename does not match REQ-NNN-slug.md pattern"
    return 1
  fi

  # Parse frontmatter (between first two --- lines)
  local in_front=0
  local front_done=0
  local front_text=""
  while IFS= read -r line; do
    if [[ "$line" == "---" && $in_front -eq 0 ]]; then
      in_front=1
      continue
    fi
    if [[ "$line" == "---" && $in_front -eq 1 ]]; then
      front_done=1
      break
    fi
    if [[ $in_front -eq 1 ]]; then
      front_text+="$line"$'\n'
    fi
  done < "$file"

  if [[ $front_done -eq 0 ]]; then
    echo "ERROR [$filename]: no YAML frontmatter found (expected --- delimiters)"
    return 1
  fi

  # Extract individual fields
  local req_id status phase milestone priority owner
  req_id=$(echo "$front_text"    | grep -E '^req_id:'   | sed 's/req_id:[[:space:]]*//')
  status=$(echo "$front_text"    | grep -E '^status:'   | sed 's/status:[[:space:]]*//')
  phase=$(echo "$front_text"     | grep -E '^phase:'    | sed 's/phase:[[:space:]]*//')
  milestone=$(echo "$front_text" | grep -E '^milestone:'| sed 's/milestone:[[:space:]]*//')
  priority=$(echo "$front_text"  | grep -E '^priority:' | sed 's/priority:[[:space:]]*//')
  owner=$(echo "$front_text"     | grep -E '^owner:'    | sed 's/owner:[[:space:]]*//')
  local depends_line
  depends_line=$(echo "$front_text" | grep -E '^depends_on:' | sed 's/depends_on:[[:space:]]*//')

  # req_id must match filename prefix
  if [[ "$req_id" != "$expected_id" ]]; then
    echo "ERROR [$filename]: req_id '$req_id' does not match filename prefix '$expected_id'"
    ((file_errors++))
  fi

  # status must be a known value
  local valid_status=0
  for s in "${VALID_STATUSES[@]}"; do
    [[ "$status" == "$s" ]] && valid_status=1 && break
  done
  if [[ $valid_status -eq 0 ]]; then
    echo "ERROR [$filename]: invalid status '$status' (valid: ${VALID_STATUSES[*]})"
    ((file_errors++))
  fi

  # phase must be a known value
  local valid_phase=0
  for p in "${VALID_PHASES[@]}"; do
    [[ "$phase" == "$p" ]] && valid_phase=1 && break
  done
  if [[ $valid_phase -eq 0 ]]; then
    echo "ERROR [$filename]: invalid phase '$phase' (valid: ${VALID_PHASES[*]})"
    ((file_errors++))
  fi

  # priority must be a known value
  local valid_priority=0
  for pr in "${VALID_PRIORITIES[@]}"; do
    [[ "$priority" == "$pr" ]] && valid_priority=1 && break
  done
  if [[ $valid_priority -eq 0 ]]; then
    echo "ERROR [$filename]: invalid priority '$priority' (valid: ${VALID_PRIORITIES[*]})"
    ((file_errors++))
  fi

  # milestone must be non-empty
  if [[ -z "$milestone" ]]; then
    echo "ERROR [$filename]: milestone field is missing or empty"
    ((file_errors++))
  fi

  # owner must be non-empty
  if [[ -z "$owner" ]]; then
    echo "ERROR [$filename]: owner field is missing or empty"
    ((file_errors++))
  fi

  # depends_on: validate each referenced REQ exists
  # Format: [] or [REQ-001] or [REQ-001, REQ-002]
  if [[ "$depends_line" != "[]" && -n "$depends_line" ]]; then
    # Strip brackets and split by comma
    local deps_clean
    deps_clean=$(echo "$depends_line" | tr -d '[]' | tr ',' '\n' | tr -d ' ')
    while IFS= read -r dep; do
      dep=$(echo "$dep" | tr -d '[:space:]')
      [[ -z "$dep" ]] && continue
      if ! req_id_known "$dep"; then
        echo "ERROR [$filename]: depends_on references unknown REQ '$dep'"
        ((file_errors++))
      fi
    done <<< "$deps_clean"
  fi

  # Check required markdown sections exist
  local file_content
  file_content=$(cat "$file")
  for section in "${REQUIRED_SECTIONS[@]}"; do
    if ! grep -qF "$section" "$file"; then
      echo "ERROR [$filename]: missing required section '$section'"
      ((file_errors++))
    fi
  done

  if [[ $file_errors -eq 0 ]]; then
    echo "OK    [$filename]: req_id=$req_id status=$status phase=$phase priority=$priority"
  fi

  return $file_errors
}

# Main loop
echo "=== FaultAtlas Requirements Validator ==="
echo "Scanning: $TASKS_DIR"
echo ""

found=0
for file in "$TASKS_DIR"/REQ-*.md; do
  [[ -f "$file" ]] || continue
  found=$((found + 1))
  if ! check_file "$file"; then
    ERRORS=$((ERRORS + 1))
  fi
done

echo ""
if [[ $found -eq 0 ]]; then
  echo "WARNING: no REQ-*.md files found in $TASKS_DIR"
  exit 0
fi

echo "=== Result: $found requirements checked, $ERRORS with errors ==="

if [[ $ERRORS -gt 0 ]]; then
  exit 1
fi
exit 0
