#!/usr/bin/env bash
# setup-branch-protection.sh — Configure GitHub branch protection for rushwing/faultatlas
#
# Requires: gh CLI authenticated with repo admin permissions
#
# Usage:
#   ./scripts/ci/setup-branch-protection.sh [--dry-run]
#
# What this configures on main:
#   - Require PR before merging (no direct pushes)
#   - Require 1 approving review
#   - Dismiss stale reviews on new commits
#   - Require status checks to pass:
#       * CI / Lint & Type Check
#       * CI / Unit Tests
#       * Requirements Format
#       * Secrets Scan
#   - Block merge if any required check is failing
#   - Require branches to be up to date before merging
#   - Do NOT allow force pushes
#   - Do NOT allow deletions

set -euo pipefail

REPO="rushwing/faultatlas"
BRANCH="main"
DRY_RUN=false

for arg in "$@"; do
  [[ "$arg" == "--dry-run" ]] && DRY_RUN=true
done

echo "=== FaultAtlas Branch Protection Setup ==="
echo "Repository: $REPO"
echo "Branch:     $BRANCH"
echo "Dry run:    $DRY_RUN"
echo ""

# Verify gh is available and authenticated
if ! command -v gh &>/dev/null; then
  echo "ERROR: gh CLI not found. Install from https://cli.github.com/"
  exit 1
fi

if ! gh auth status &>/dev/null; then
  echo "ERROR: gh CLI not authenticated. Run: gh auth login"
  exit 1
fi

# Verify repo exists and we have admin access
if ! gh repo view "$REPO" &>/dev/null; then
  echo "ERROR: Cannot access repository $REPO"
  exit 1
fi

echo "Repository access verified."
echo ""

# Build the branch protection payload
PAYLOAD=$(cat <<'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "CI / Lint & Type Check",
      "CI / Unit Tests",
      "Requirements Format",
      "Secrets Scan"
    ]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismissal_restrictions": {},
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": false
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": false
}
EOF
)

if [[ "$DRY_RUN" == "true" ]]; then
  echo "DRY RUN — would send PUT branches/$BRANCH/protection with:"
  echo "$PAYLOAD" | python3 -m json.tool
  echo ""
  echo "Run without --dry-run to apply."
  exit 0
fi

echo "Applying branch protection rules..."
echo ""

gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "/repos/$REPO/branches/$BRANCH/protection" \
  --input - <<< "$PAYLOAD"

echo ""
echo "=== Branch protection applied ==="
echo ""
echo "Required status checks:"
echo "  - CI / Lint & Type Check     (.github/workflows/ci.yml)"
echo "  - CI / Unit Tests            (.github/workflows/ci.yml)"
echo "  - Requirements Format        (.github/workflows/requirements.yml)"
echo "  - Secrets Scan               (.github/workflows/secrets-scan.yml)"
echo ""
echo "Optional (advisory) checks — annotate PRs but do not block:"
echo "  - Requirements Merge Gate    (.github/workflows/requirements-merge-gate.yml)"
echo "  - Prompt Change Gate         (.github/workflows/prompt-protection.yml)"
echo ""
echo "To verify: gh api /repos/$REPO/branches/$BRANCH/protection | python3 -m json.tool"
