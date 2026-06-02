#!/usr/bin/env python3
"""CI gate: engine source paths with user-facing authoring implications must be
shipped together with their teaching SKILL.md updates.

Context: in the 14 canopy PRs shipped on 2026-06-01, only #108, #111, #113,
and #115 explicitly touched SKILL.md when they should have. The others left
their best practices undocumented for weeks — PRs #100, #101, #102, #105,
#112, #114 each shipped new spec-author surface (Scene.url, must_succeed,
prefix syntax, snapshot flags, scroll_to cursor glide, Scene.viewport)
without updating SKILL.md. Future agents doing /canopy:ddd inherited the
engine fixes but not the authoring patterns, so the same gaps got audited
and patched in #115 + #116. This gate prevents the next drift cycle.

Usage (as a CLI from GitHub Actions):

    python .github/scripts/docs_sync_check.py \\
        --pr-number "$PR_NUMBER" \\
        --repo "$GITHUB_REPOSITORY"

The script shells out to `gh pr view` for changed files + PR body. It exits
0 on pass (including the opt-out path) and 1 on a real miss. It prints a
markdown-friendly failure block to stdout that GitHub Actions surfaces in
the job log.

For testing, the pure logic lives in `check_docs_sync(changed, pr_body)`
which takes plain inputs and returns a structured result — no subprocess
required.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Iterable


# Mapping of engine source path → required teaching SKILL.md docs.
#
# When a PR touches a key here, every value path MUST also be in the PR's
# changed-files set (or the PR body must carry a `Docs-not-needed:` opt-out
# marker). The three categories below match the structural enforcement plan:
#
#   1. Spec model surface (new Action verb or new Action field) → ddd-spec
#      teaches the verb/field to authors; walkthrough teaches the same on the
#      interactive-recording side.
#   2. Recorder primitives (the engine that interprets actions) — same audience
#      as (1); when a new primitive lands, both author-facing docs need to know.
#   3. record_video CLI flag set → ddd-run orchestrator skill carries the
#      canonical default flag set.
#   4. Concept-eval rubric dimensions → ddd-concept-eval SKILL.md documents the
#      weight, routing, and scope.
TRIGGER_PATHS: dict[str, list[str]] = {
    "scripts/ddd/schemas/models.py": [
        "plugins/canopy/skills/ddd-spec/SKILL.md",
        "plugins/canopy/skills/walkthrough/SKILL.md",
    ],
    "scripts/walkthrough/_lib/recorder.py": [
        "plugins/canopy/skills/ddd-spec/SKILL.md",
        "plugins/canopy/skills/walkthrough/SKILL.md",
    ],
    "scripts/walkthrough/record_video.py": [
        "plugins/canopy/skills/ddd-run/SKILL.md",
    ],
    "plugins/canopy/skills/ddd-concept-eval/rubric.yaml": [
        "plugins/canopy/skills/ddd-concept-eval/SKILL.md",
    ],
}

OPT_OUT_PREFIX = "Docs-not-needed:"


@dataclass
class CheckResult:
    """Outcome of a docs-sync check."""

    passed: bool
    # When the opt-out marker was honored, this captures the reason text for
    # logging — `passed` is True in that case.
    opt_out_reason: str | None = None
    # Per-trigger findings — one entry per source path that was touched but
    # whose required docs weren't all updated.
    missing: list["TriggerMiss"] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return not self.passed


@dataclass
class TriggerMiss:
    trigger: str
    missing_docs: list[str]


def has_opt_out_marker(pr_body: str | None) -> tuple[bool, str | None]:
    """Detect a `Docs-not-needed: <reason>` line in the PR body.

    Returns (present, reason). When present is True, reason is the trimmed
    text after the marker.
    """
    if not pr_body:
        return False, None
    for raw_line in pr_body.splitlines():
        line = raw_line.strip()
        if line.startswith(OPT_OUT_PREFIX):
            reason = line[len(OPT_OUT_PREFIX) :].strip()
            return True, reason or "(no reason given)"
    return False, None


def check_docs_sync(
    changed: Iterable[str],
    pr_body: str | None,
    trigger_paths: dict[str, list[str]] | None = None,
) -> CheckResult:
    """Pure logic: given changed files + PR body, produce a CheckResult.

    No subprocess, no I/O — fully unit-testable.
    """
    triggers = trigger_paths if trigger_paths is not None else TRIGGER_PATHS
    changed_set = set(changed)

    misses: list[TriggerMiss] = []
    for trigger, required_docs in triggers.items():
        if trigger not in changed_set:
            continue
        missing = [d for d in required_docs if d not in changed_set]
        if missing:
            misses.append(TriggerMiss(trigger=trigger, missing_docs=missing))

    if not misses:
        return CheckResult(passed=True)

    # Misses exist — check for the opt-out marker before failing.
    opted_out, reason = has_opt_out_marker(pr_body)
    if opted_out:
        return CheckResult(passed=True, opt_out_reason=reason, missing=misses)

    return CheckResult(passed=False, missing=misses)


def format_failure_message(result: CheckResult) -> str:
    """Human-readable failure block for the GitHub Actions log."""
    lines: list[str] = []
    lines.append(
        "docs-sync: this PR changed source paths that have user-facing"
        " authoring implications, but didn't touch the corresponding skill"
        " docs."
    )
    lines.append("")
    for miss in result.missing:
        lines.append(f"  - {miss.trigger} changed -> also update:")
        for doc in miss.missing_docs:
            lines.append(f"      {doc}")
    lines.append("")
    lines.append(
        "Why this matters: PRs #100, #101, #102, #105, #112, #114 each shipped"
        " new spec-author surface (Scene.url, must_succeed, prefix syntax,"
        " snapshot flags, scroll_to cursor glide, Scene.viewport) without"
        " updating SKILL.md. Future agents doing /canopy:ddd inherited the"
        " engine fixes but not the authoring patterns, so the same gaps got"
        " audited and patched in #115 + #116."
    )
    lines.append("")
    lines.append("To pass:")
    lines.append("  1. Update the listed SKILL.md file(s) to teach the new surface, OR")
    lines.append(
        '  2. Add a line "Docs-not-needed: <one-sentence reason>" to the PR body'
    )
    lines.append(
        "     if this is genuinely an engine-internal change (refactor, perf fix,"
    )
    lines.append("     bug fix that doesn't change the authoring contract).")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI / subprocess plumbing — only exercised on GitHub Actions, not in tests.
# ---------------------------------------------------------------------------


def _gh_pr_view(pr_number: str, repo: str, jq_path: str) -> str:
    """Call `gh pr view` and return raw JSON-decoded value at jq_path.

    Uses `--json` + `--jq` so we get the deserialized value out directly.
    """
    cmd = [
        "gh",
        "pr",
        "view",
        pr_number,
        "--repo",
        repo,
        "--json",
        jq_path.split(".")[0] if jq_path else "",
    ]
    # `--jq` lets us project sub-fields; default to identity.
    cmd.extend(["--jq", "." + jq_path if not jq_path.startswith(".") else jq_path])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return proc.stdout


def fetch_pr_context(pr_number: str, repo: str) -> tuple[list[str], str]:
    """Pull changed file paths + PR body from gh.

    Returns (changed_paths, pr_body). Both are best-effort — on gh failure,
    raises CalledProcessError up; the workflow step surfaces it.
    """
    files_proc = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            pr_number,
            "--repo",
            repo,
            "--json",
            "files",
            "--jq",
            ".files[].path",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    changed = [line for line in files_proc.stdout.splitlines() if line.strip()]

    body_proc = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            pr_number,
            "--repo",
            repo,
            "--json",
            "body",
            "--jq",
            ".body",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    pr_body = body_proc.stdout

    return changed, pr_body


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pr-number",
        required=False,
        default=os.environ.get("PR_NUMBER"),
        help="PR number (or set PR_NUMBER env var)",
    )
    parser.add_argument(
        "--repo",
        required=False,
        default=os.environ.get("GITHUB_REPOSITORY"),
        help="owner/repo (or set GITHUB_REPOSITORY env var)",
    )
    parser.add_argument(
        "--changed-files",
        help="Newline- or comma-separated list of changed files (test helper).",
    )
    parser.add_argument(
        "--pr-body",
        help="PR body text passed directly (test helper).",
    )
    args = parser.parse_args(argv)

    if args.changed_files is not None:
        # Test / local invocation — skip gh entirely.
        sep = "\n" if "\n" in args.changed_files else ","
        changed = [p.strip() for p in args.changed_files.split(sep) if p.strip()]
        pr_body = args.pr_body or ""
    else:
        if not args.pr_number or not args.repo:
            print(
                "ERROR: --pr-number and --repo (or PR_NUMBER and"
                " GITHUB_REPOSITORY env) are required when --changed-files"
                " is not given.",
                file=sys.stderr,
            )
            return 2
        changed, pr_body = fetch_pr_context(args.pr_number, args.repo)

    result = check_docs_sync(changed, pr_body)

    if result.passed:
        if result.opt_out_reason is not None:
            # Opted out — log the reason so reviewers can spot misuse.
            triggered = ", ".join(m.trigger for m in result.missing)
            print(
                f"docs-sync skipped: {result.opt_out_reason}"
                f" (triggered by: {triggered})"
            )
        else:
            print("docs-sync: ok (no trigger paths touched, or all docs updated)")
        return 0

    # Failure path — print the structured message and exit 1.
    msg = format_failure_message(result)
    print(msg)
    # GitHub Actions annotation for visibility in the PR's Checks tab.
    summary = "; ".join(
        f"{m.trigger} missing {','.join(m.missing_docs)}" for m in result.missing
    )
    print(f"::error::docs-sync gate failed: {summary}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
