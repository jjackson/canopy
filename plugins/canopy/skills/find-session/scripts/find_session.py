#!/usr/bin/env python3
"""Find another active Claude Code session and digest what it's doing.

Single-purpose lookup for the common ask: "find my OTHER active session on
repo X and tell me what it's been working on." Walks ~/.claude/projects/,
excludes the current session, ranks candidates by recency, and prints a
digest (worktree, branch, recent commits, recent human prompts, dirty files)
the calling agent can act on without re-running shell.

Stdlib only — safe to run with system python3 (no PyYAML / deps).

Usage:
    find_session.py [TARGET] [options]

    TARGET   repo-slug substring (e.g. "connect-labs"), or a worktree path.
             Omit to consider every recent session that isn't this one.

Options:
    --hours N            recency window in hours (default: 24)
    --max-prompts N      human prompts to surface per candidate (default: 20)
    --commits N          recent commits to show for the top candidate (default: 8)
    --exclude-session ID session id to treat as "this session"
                         (default: $CLAUDE_CODE_SESSION_ID)
    --top N              candidates to fully digest (default: 1; menu beyond that)
    --json               emit machine-readable JSON instead of a text digest
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"

# Prefixes that mark a "user" message as harness noise, not a human prompt.
_NOISE_PREFIXES = (
    "<system-reminder",
    "<command-name",
    "<command-message",
    "<command-args",
    "<local-command-stdout",
    "<local-command-stderr",
    "<local-command-caveat",
    "<task-notification",
    "<system>",
    "Caveat:",
    "[Request interrupted",
)


def _encode_cwd(path: str) -> str:
    """Claude Code encodes a project dir name by replacing every '/' with '-'."""
    return path.replace("/", "-")


def _iter_human_prompts(path: Path):
    """Yield human-authored prompt strings from a transcript, newest last.

    Filters out sidechain (subagent) turns, tool-result blocks, and harness
    noise (system-reminders, slash-command wrappers, interrupt markers).
    """
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "user" or entry.get("isSidechain"):
                continue
            msg = entry.get("message", {})
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                # list content == tool_result or block message; skip.
                continue
            text = content.strip()
            if not text or text.startswith(_NOISE_PREFIXES):
                continue
            yield text


def _session_meta(path: Path):
    """Pull cwd + gitBranch off the first entry that carries them."""
    cwd, branch = None, None
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if cwd is None and entry.get("cwd"):
                    cwd = entry["cwd"]
                if branch is None and entry.get("gitBranch"):
                    branch = entry["gitBranch"]
                if cwd and branch:
                    break
    except OSError:
        pass
    return cwd, branch


def _candidate_dirs(target: str | None):
    """Resolve which project dirs to scan from the target hint."""
    if not PROJECTS_DIR.is_dir():
        return []
    if not target:
        return [d for d in PROJECTS_DIR.iterdir() if d.is_dir()]
    # A path-like target: encode it and prefix-match (handles worktree paths).
    if "/" in target:
        encoded = _encode_cwd(os.path.abspath(os.path.expanduser(target)))
        exact = [d for d in PROJECTS_DIR.iterdir() if d.is_dir() and encoded in d.name]
        if exact:
            return exact
        # Fall back to the leaf segment only when nothing matched the full path.
        leaf = encoded.rstrip("-").split("-")[-1]
        return [
            d for d in PROJECTS_DIR.iterdir()
            if d.is_dir() and leaf and leaf in d.name
        ]
    # A slug substring.
    return [d for d in PROJECTS_DIR.iterdir() if d.is_dir() and target in d.name]


def _git(cwd: str, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def collect(target, exclude_session, hours, max_prompts):
    """Build the ranked candidate list."""
    cutoff = time.time() - hours * 3600
    candidates = []
    for d in _candidate_dirs(target):
        for jsonl in d.glob("*.jsonl"):
            session_id = jsonl.stem
            if exclude_session and session_id == exclude_session:
                continue
            try:
                st = jsonl.stat()
            except OSError:
                continue
            if st.st_size == 0 or st.st_mtime < cutoff:
                continue
            cwd, branch = _session_meta(jsonl)
            prompts = list(_iter_human_prompts(jsonl))
            if not prompts:
                continue  # no human turns => not a real working session
            candidates.append({
                "session_id": session_id,
                "transcript": str(jsonl),
                "project_key": d.name,
                "cwd": cwd,
                "branch": branch,
                "mtime": st.st_mtime,
                "age_minutes": round((time.time() - st.st_mtime) / 60, 1),
                "prompts": prompts[-max_prompts:],
                "prompt_count": len(prompts),
            })
    candidates.sort(key=lambda c: c["mtime"], reverse=True)
    return candidates


def _enrich_git(cand, commits):
    """Attach branch / recent commits / dirty files for a digested candidate."""
    cwd = cand.get("cwd")
    if not cwd or not Path(cwd).is_dir():
        cand["git_available"] = False
        return cand
    cand["git_available"] = True
    cand["branch"] = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD") or cand.get("branch")
    log = _git(cwd, "log", f"-{commits}", "--pretty=format:%h %s")
    cand["commits"] = log.splitlines() if log else []
    status = _git(cwd, "status", "--porcelain")
    cand["dirty"] = status.splitlines() if status else []
    return cand


def _fmt_ts(mtime):
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))


def render_text(candidates, top):
    if not candidates:
        return "No matching active session found (none within the recency window, excluding this one)."
    lines = []
    digested = candidates[:top]
    for i, c in enumerate(digested, 1):
        header = f"### Candidate {i}: {c.get('branch') or '(unknown branch)'}"
        if len(digested) == 1:
            header = f"### {c.get('branch') or '(unknown branch)'}"
        lines.append(header)
        lines.append(f"- worktree: `{c.get('cwd') or '(unknown)'}`")
        lines.append(f"- session:  `{c['session_id']}`  (modified {_fmt_ts(c['mtime'])}, {c['age_minutes']} min ago)")
        lines.append(f"- transcript: `{c['transcript']}`")
        if c.get("git_available"):
            if c.get("commits"):
                lines.append(f"- recent commits:")
                for ln in c["commits"]:
                    lines.append(f"    {ln}")
            if c.get("dirty"):
                lines.append(f"- uncommitted ({len(c['dirty'])} files):")
                for ln in c["dirty"][:20]:
                    lines.append(f"    {ln}")
            else:
                lines.append("- uncommitted: (clean)")
        elif c.get("cwd"):
            lines.append("- git: worktree path no longer exists on disk")
        lines.append(f"- recent human prompts (last {len(c['prompts'])} of {c['prompt_count']}):")
        for p in c["prompts"]:
            one = " ".join(p.split())
            if len(one) > 200:
                one = one[:197] + "..."
            lines.append(f"    • {one}")
        lines.append("")

    rest = candidates[top:]
    if rest:
        lines.append(f"### Other candidates ({len(rest)})")
        for c in rest:
            one = " ".join(c["prompts"][-1].split())
            if len(one) > 80:
                one = one[:77] + "..."
            lines.append(
                f"- `{c.get('branch') or '?'}` · {c['age_minutes']} min ago · "
                f"`{c['session_id'][:8]}` · last: {one}"
            )
        lines.append("")
        # Ambiguity hint: multiple candidates within a few minutes of the top.
        close = [c for c in rest if abs(c["mtime"] - candidates[0]["mtime"]) < 300]
        if close:
            lines.append(
                f"⚠️  {len(close)} other session(s) were active within ~5 min of the "
                f"top candidate — confirm with the user which one they mean if it matters."
            )
    return "\n".join(lines).rstrip()


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find another active Claude Code session.")
    ap.add_argument("target", nargs="?", default=None,
                    help="repo-slug substring or worktree path (default: any session but this one)")
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--max-prompts", type=int, default=20)
    ap.add_argument("--commits", type=int, default=8)
    ap.add_argument("--exclude-session", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    ap.add_argument("--top", type=int, default=1)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    candidates = collect(args.target, args.exclude_session, args.hours, args.max_prompts)
    for c in candidates[:args.top]:
        _enrich_git(c, args.commits)

    if args.json:
        print(json.dumps(candidates, indent=2))
    else:
        print(render_text(candidates, args.top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
