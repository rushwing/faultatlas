#!/usr/bin/env python3
"""
check-prompt-change.py — Validate PR description when prompts.py is changed.

Called by .github/workflows/prompt-protection.yml

When a PR modifies prompts.py or prompt_builder.py, the PR author must
acknowledge the eval process in the PR body. This script enforces that gate.

Required acknowledgments (at least ONE must be present):
  - "eval-prompt" or "make eval-prompt" — ran stability check
  - "eval-prompt-regression" or "make eval-prompt-regression" — ran regression check
  - "layer1_stability" — referenced the stability metric
  - "faithfulness" — referenced the faithfulness regression metric

Usage:
    python3 scripts/ci/check-prompt-change.py \
        --pr-body "$PR_BODY" \
        --changed-files "services/api/app/agents/prompts.py"

Exit codes:
    0 — PR body contains sufficient eval acknowledgment
    1 — PR body missing required eval acknowledgment
"""

import argparse
import re
import sys

# At least this many of these tokens must appear in the PR body
REQUIRED_TOKENS = [
    r"eval[\-_]prompt",
    r"eval[\-_]prompt[\-_]regression",
    r"layer1_stability",
    r"faithfulness",
    r"prompt_baseline",
    r"make eval",
]

# Minimum number of distinct required tokens that must match
MIN_MATCHES = 1

# Files whose change triggers this check
PROMPT_FILES = {
    "services/api/app/agents/prompts.py",
    "services/api/app/agents/prompt_builder.py",
}


def check_pr_body(pr_body: str, changed_files: list[str]) -> tuple[bool, list[str]]:
    """
    Check if the PR body contains adequate eval acknowledgment.
    Returns (passed: bool, messages: list[str])
    """
    messages = []

    # Normalize changed files
    changed_set = {f.strip().lstrip("./") for f in changed_files if f.strip()}

    # Check if any prompt files are in the changed set
    # Accept both exact match and suffix match (CI may give full absolute paths)
    prompt_changed = False
    for cf in changed_set:
        if cf in PROMPT_FILES:
            prompt_changed = True
            break
        for pf in PROMPT_FILES:
            # e.g. cf="/home/runner/work/repo/services/api/app/agents/prompts.py"
            if cf.endswith(pf):
                prompt_changed = True
                break
        if prompt_changed:
            break

    if not prompt_changed:
        messages.append("INFO: no prompt files in changed set — no eval acknowledgment required")
        return True, messages

    messages.append("PROMPT FILE CHANGED — checking PR body for eval acknowledgment...")

    if not pr_body or not pr_body.strip():
        messages.append(
            "ERROR: PR body is empty. When changing prompts.py, you must document "
            "the eval results in the PR description."
        )
        messages.append("")
        messages.append("Required: mention at least one of:")
        for token in REQUIRED_TOKENS:
            messages.append(f"  - {token}")
        return False, messages

    body_lower = pr_body.lower()
    matched_tokens = []

    for token_pattern in REQUIRED_TOKENS:
        if re.search(token_pattern, body_lower, re.IGNORECASE):
            matched_tokens.append(token_pattern)

    if len(matched_tokens) >= MIN_MATCHES:
        messages.append(
            f"OK: PR body mentions eval acknowledgment "
            f"({len(matched_tokens)} matching token(s): {matched_tokens})"
        )
        return True, messages

    messages.append(
        f"ERROR: PR body does not mention eval results. "
        f"Found 0/{MIN_MATCHES} required eval acknowledgment tokens."
    )
    messages.append("")
    messages.append(
        "When changing prompts.py, add an eval note to your PR description. Example:"
    )
    messages.append("")
    messages.append("  ## Eval Results")
    messages.append("  - `make eval-prompt` passed (layer1_stability = 1.00)")
    messages.append("  - `make eval-prompt-regression` passed (faithfulness delta = +0.02)")
    messages.append("  - Updated prompt_baseline_v1.json")
    messages.append("")
    messages.append(f"Required tokens (at least {MIN_MATCHES}):")
    for token in REQUIRED_TOKENS:
        messages.append(f"  - {token}")

    return False, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Prompt change PR body validator")
    parser.add_argument("--pr-body", default="", help="Pull request body text")
    parser.add_argument(
        "--changed-files",
        default="",
        help="Space or newline separated list of changed file paths",
    )
    args = parser.parse_args()

    # Accept both space and newline separated files
    changed_files = re.split(r"[\s\n]+", args.changed_files) if args.changed_files else []
    changed_files = [f for f in changed_files if f.strip()]

    print("=== Prompt Change Gate ===")
    print(f"Changed files: {changed_files}")
    print()

    passed, messages = check_pr_body(args.pr_body, changed_files)

    for msg in messages:
        print(msg)

    print()
    if passed:
        print("=== GATE PASSED ===")
        return 0
    else:
        print("=== GATE BLOCKED ===")
        print()
        print("See docs/adr/ADR-004-eval-strategy.md for the full prompt eval process.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
