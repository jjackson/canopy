"""Generic git-repo evidence helpers — FRAMEWORK tier (agent-agnostic, stdlib + git only).

Extracted from verify_findings (PRODUCT) so FRAMEWORK modules can build the same
"is this already in origin/main?" evidence without importing a product module. Two
consumers today: verify_findings (proposals) and agent_review's source-verification
gate (findings). See src/orchestrator/TIERS.md.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

# Backtick-quoted identifiers in a piece of text — file paths, function names, env
# vars, config keys. The things worth grepping the current tree for.
SYMBOL_RX = re.compile(r"`([^`]{2,80})`")


def git_log_recent(repo: Path, since: str = "14 days ago") -> str:
    """Recent origin/main commits (short hash + date + subject), '' on any failure."""
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "log", "origin/main",
             f"--since={since}", "--pretty=format:%h %ad %s",
             "--date=short"],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        ).strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return ""


def changelog_head(repo: Path, lines: int = 200) -> str:
    """First `lines` of the repo's CHANGELOG.md, '' if absent/unreadable."""
    cl = repo / "CHANGELOG.md"
    if not cl.exists():
        return ""
    try:
        with open(cl, encoding="utf-8") as f:
            return "".join(f.readline() for _ in range(lines)).rstrip()
    except OSError:
        return ""


def grep_repo(repo: Path, symbols: list[str]) -> str:
    """`git grep` each symbol in the current tree; a labelled block per symbol with up
    to 5 hits (or '(no hits)'). '' if no symbols given."""
    if not symbols:
        return ""
    parts: list[str] = []
    for sym in symbols:
        try:
            out = subprocess.check_output(
                ["git", "-C", str(repo), "grep", "-n", "--",
                 sym, "--", ":!.git", ":!node_modules"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            out = ""
        out = out.strip()
        if out:
            head = "\n".join(out.splitlines()[:5])
            parts.append(f"=== `{sym}` ===\n{head}")
        else:
            parts.append(f"=== `{sym}` ===\n(no hits)")
    return "\n\n".join(parts)
