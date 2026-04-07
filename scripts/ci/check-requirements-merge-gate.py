#!/usr/bin/env python3
"""
check-requirements-merge-gate.py — REQ status gate for PR merges.

Called by .github/workflows/requirements-merge-gate.yml

Reads the GitHub event JSON to find:
  - Changed files in the PR
  - PR body text and any REQ ID references

Checks:
  1. REQ files changed in the PR must not be in 'draft' or 'cancelled' status.
  2. REQ IDs referenced in the PR body must exist and not be 'draft'.
  3. With --autofix: advances 'ready' → 'in-progress' for changed REQ files
     and writes `autofixed=true` to GITHUB_OUTPUT for the bot-commit step.

Usage (CI):
    python3 scripts/ci/check-requirements-merge-gate.py \
        --event-path "$GITHUB_EVENT_PATH" \
        --github-output "$GITHUB_OUTPUT" \
        --autofix

Usage (local):
    python3 scripts/ci/check-requirements-merge-gate.py \
        --event-path /tmp/event.json

Exit codes:
    0 — gate passes (or autofix succeeded)
    1 — gate blocked (draft REQ or missing REQ referenced)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

MERGE_ALLOWED_STATUSES = {"ready", "in-progress", "in-review", "done"}
BLOCKED_STATUSES = {"draft", "cancelled"}
REQ_REF_PATTERN = re.compile(r"\bREQ-\d{3}\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Frontmatter parsing (pure stdlib fallback if PyYAML not available)
# ---------------------------------------------------------------------------

def parse_frontmatter(path: Path) -> dict:
    content = path.read_text()
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return {}
    front_block = "\n".join(lines[1:end_idx])
    if HAS_YAML:
        try:
            return yaml.safe_load(front_block) or {}
        except yaml.YAMLError:
            pass
    # Fallback: naive key: value parser
    result = {}
    for line in front_block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def find_req_file(req_id: str, tasks_dir: Path) -> Path | None:
    for subdir in ("active", "done"):
        d = tasks_dir / subdir
        if not d.exists():
            continue
        for f in d.glob(f"{req_id.upper()}-*.md"):
            return f
    return None


# ---------------------------------------------------------------------------
# Load GitHub event
# ---------------------------------------------------------------------------

def load_event(event_path: str) -> dict:
    p = Path(event_path)
    if not p.exists():
        print(f"WARNING: event file not found at {event_path}, using empty event")
        return {}
    with p.open() as f:
        return json.load(f)


def extract_changed_files(event: dict) -> list[str]:
    """
    Extract changed file paths from a pull_request event.
    GitHub doesn't embed file lists in the event JSON — we use the commits list.
    For CI we rely on the GITHUB_BASE_REF / GITHUB_HEAD_REF approach via git diff.
    Falls back to empty list if not determinable.
    """
    # Try to get from git diff (available in checkout context)
    base = os.environ.get("GITHUB_BASE_REF", "")
    head = os.environ.get("GITHUB_HEAD_REF", "")
    if base and head:
        import subprocess
        try:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"origin/{base}...HEAD"],
                capture_output=True, text=True, check=True
            )
            return [f for f in result.stdout.splitlines() if f.strip()]
        except subprocess.CalledProcessError:
            pass
    return []


def extract_pr_body(event: dict) -> str:
    return (
        event.get("pull_request", {}).get("body") or ""
    )


# ---------------------------------------------------------------------------
# Gate logic
# ---------------------------------------------------------------------------

def check_changed_reqs(changed_files: list[str], tasks_dir: Path) -> list[str]:
    errors = []
    for filepath in changed_files:
        p = Path(filepath)
        if not (p.name.startswith("REQ-") and p.name.endswith(".md")):
            continue
        if not p.exists():
            continue
        front = parse_frontmatter(p)
        status = front.get("status", "unknown")
        if status in BLOCKED_STATUSES:
            errors.append(
                f"BLOCKED {p.name}: status='{status}' — "
                f"must be 'ready' or beyond before merging"
            )
        else:
            print(f"  OK {p.name}: status='{status}'")
    return errors


def check_pr_references(pr_body: str, tasks_dir: Path) -> list[str]:
    errors = []
    if not pr_body:
        return errors
    seen: set[str] = set()
    for ref in REQ_REF_PATTERN.findall(pr_body):
        ref_upper = ref.upper()
        if ref_upper in seen:
            continue
        seen.add(ref_upper)
        req_file = find_req_file(ref_upper, tasks_dir)
        if req_file is None:
            errors.append(
                f"BLOCKED: PR references '{ref_upper}' but no matching file "
                f"found in {tasks_dir}/active/ or {tasks_dir}/done/"
            )
            continue
        front = parse_frontmatter(req_file)
        status = front.get("status", "unknown")
        if status == "draft":
            errors.append(
                f"BLOCKED: '{ref_upper}' ({req_file.name}) is still 'draft' — "
                f"promote to 'ready' before merging"
            )
        elif status == "cancelled":
            errors.append(
                f"WARNING: '{ref_upper}' ({req_file.name}) is 'cancelled' — "
                f"verify this reference is intentional"
            )
        else:
            print(f"  OK ref {ref_upper}: status='{status}'")
    return errors


def autofix_statuses(changed_files: list[str]) -> list[str]:
    """Advance ready → in-progress. Returns list of advanced filenames."""
    advanced = []
    for filepath in changed_files:
        p = Path(filepath)
        if not (p.name.startswith("REQ-") and p.name.endswith(".md")):
            continue
        if not p.exists():
            continue
        front = parse_frontmatter(p)
        if front.get("status") == "ready":
            content = p.read_text()
            new_content = content.replace("status: ready", "status: in-progress", 1)
            if new_content != content:
                p.write_text(new_content)
                advanced.append(p.name)
                print(f"  ADVANCED {p.name}: ready → in-progress")
    return advanced


def write_github_output(key: str, value: str, output_file: str | None) -> None:
    if not output_file:
        return
    with open(output_file, "a") as f:
        # Multi-line safe encoding
        if "\n" in value:
            delimiter = "EOF"
            f.write(f"{key}<<{delimiter}\n{value}\n{delimiter}\n")
        else:
            f.write(f"{key}={value}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="REQ status merge gate")
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH", ""))
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    parser.add_argument("--tasks-dir", default="tasks")
    parser.add_argument(
        "--autofix",
        action="store_true",
        help="Advance ready→in-progress for changed REQs",
    )
    args = parser.parse_args()

    tasks_dir = Path(args.tasks_dir)
    event = load_event(args.event_path) if args.event_path else {}
    changed_files = extract_changed_files(event)
    pr_body = extract_pr_body(event)

    print("=== FaultAtlas REQ Merge Gate ===")
    print(f"Tasks dir:     {tasks_dir}")
    print(f"Changed files: {len(changed_files)}")
    print(f"Autofix:       {args.autofix}")
    print()

    errors: list[str] = []
    print("--- Checking changed REQ files ---")
    errors.extend(check_changed_reqs(changed_files, tasks_dir))

    print()
    print("--- Checking PR body references ---")
    errors.extend(check_pr_references(pr_body, tasks_dir))

    # Autofix: advance statuses if everything is clean
    autofixed: list[str] = []
    if args.autofix and not errors:
        print()
        print("--- Advancing statuses ---")
        autofixed = autofix_statuses(changed_files)

    # Write GitHub Actions outputs
    autofixed_flag = "true" if autofixed else "false"
    summary_lines = []
    if autofixed:
        summary_lines.append(f"Auto-advanced {len(autofixed)} requirement(s): {', '.join(autofixed)}")
    if errors:
        summary_lines.extend(errors)
    else:
        summary_lines.append("All requirement status checks passed.")

    summary = "\n".join(summary_lines)
    write_github_output("autofixed", autofixed_flag, args.github_output)
    write_github_output("summary", summary, args.github_output)

    print()
    if errors:
        print("=== GATE BLOCKED ===")
        for e in errors:
            print(f"  {e}")
        return 1

    print("=== GATE PASSED ===")
    if autofixed:
        print(f"  Auto-advanced: {', '.join(autofixed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
