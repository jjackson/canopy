"""Agent self-improvement lens — point canopy's analyze→propose loop at an agent's turns.

Build 2 of docs/agent-operating-model.md: the active learning loop reef never had. Reviews an
agent's recent TURN transcripts for operating-model friction — dropped checklist steps, tool
failures/retries, gating blocks, repeated manual work that should be a skill — and produces
findings + recommended fixes scoped to the agent's repo (skill edit / hook rule / CLAUDE update /
channel fix). The deterministic friction extraction is the testable core; an optional claude -p
pass synthesizes ranked findings on top of it (the evaluator–optimizer step, §6.3).

Reuses the existing machinery: transcripts.py (parse/extract), repo_paths.py (resolve), and the
analyzer's claude -p pattern. It does NOT fork the pipeline — it's a lens on the same loop.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from orchestrator.repo_paths import resolve_repo_path
from orchestrator.transcripts import (
    extract_assistant_text,
    extract_tool_calls,
    read_transcript,
)

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

# Operating-model friction taxonomy. Findings get tagged with one of these.
FRICTION_TYPES = (
    "tool_failure",    # a tool call errored
    "retry_loop",      # the same tool was re-tried after a failure
    "gating_block",    # a PreToolUse hook blocked an action (deny)
    "checklist_gap",   # an expected turn step never ran
    "skill_capture",   # a multi-step manual pattern that should be a skill
    "auth_friction",   # auth/credential/setup blockers
)

# Expected turn steps for an operating-model agent, with markers that evidence each ran.
# A step with no marker present in a turn is a candidate `checklist_gap`.
DEFAULT_TURN_STEPS = (
    ("preflight", (r"preflight", r"readiness")),
    ("self-review", (r"self-review", r"self review")),
    ("skill-self-check", (r"skill.?self.?check", r"did i (create|improve) a skill",
                          r"should be a skill")),
    ("workspace-refresh", (r"agent-publish", r"/agents/")),
)

_ERROR_MARKERS = re.compile(
    r"(?:^|\b)(?:error|errno|traceback|exception|failed|not found|not been used|"
    r"permission denied|blocked|fatal|✗|exit code [1-9]|"
    r"4(?:00|01|03|04|09|22|29)|5(?:00|02|03))\b",
    re.I,
)
_AUTH_MARKERS = re.compile(
    r"(?:not logged in|no token|invalid token|unauthorized|401|403|api .*not enabled|"
    r"credentials?|oauth|1password|op read|op inject)",
    re.I,
)


def resolve_agent_repo(slug_or_path: str) -> Path | None:
    """Resolve an agent slug or path to its repo root (must hold .claude-plugin/plugin.json)."""
    p = Path(slug_or_path).expanduser()
    if "/" in str(slug_or_path) and p.exists():
        return p if (p / ".claude-plugin" / "plugin.json").exists() else p
    rp = resolve_repo_path(slug_or_path)
    return rp


def _result_text(call: dict) -> str:
    r = call.get("result")
    if isinstance(r, list):
        return " ".join(str(b.get("text", b) if isinstance(b, dict) else b) for b in r)
    return str(r or "")


def _transcript_cwd(path: Path) -> str:
    """The cwd a transcript ran in (Claude records it per entry). '' if unknown."""
    for entry in read_transcript(path):
        cwd = entry.get("cwd")
        if cwd:
            return cwd
    return ""


def _belongs_to_agent(cwd: str, repo: Path, slug: str) -> bool:
    if not cwd:
        return False
    cwd = str(cwd)
    return (
        cwd == str(repo)
        or cwd.startswith(str(repo) + "/")
        or f"/worktrees/{slug}/" in cwd
        or cwd.rstrip("/").endswith(f"/repositories/{slug}")
    )


def find_turn_transcripts(
    repo: Path, hours: int = 168, projects_dir: Path = CLAUDE_PROJECTS
) -> list[Path]:
    """Recent transcripts whose cwd is within the agent's repo (or one of its worktrees)."""
    slug = repo.name
    if not projects_dir.exists():
        return []
    cutoff = time.time() - hours * 3600
    # Pre-filter project dirs by name (the encoded cwd contains the slug) to bound the scan.
    name_re = re.compile(rf"-{re.escape(slug)}(?:-|$)")
    out: list[tuple[float, Path]] = []
    for d in projects_dir.iterdir():
        if not d.is_dir() or not name_re.search(d.name):
            continue
        for f in d.glob("*.jsonl"):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                continue
            if _belongs_to_agent(_transcript_cwd(f), repo, slug):
                out.append((mtime, f))
    return [f for _, f in sorted(out, reverse=True)]


def friction_signals(transcript_path: Path, steps=DEFAULT_TURN_STEPS) -> dict:
    """Deterministic per-turn friction signals. No LLM — pure structural extraction."""
    entries = read_transcript(transcript_path)
    calls = extract_tool_calls(entries)
    asst_text = "\n".join(extract_assistant_text(entries)).lower()

    failures, gating_blocks, auth_hits = [], [], []
    for c in calls:
        res = _result_text(c)
        if not res:
            continue
        head = res[:600]
        is_block = "BLOCKED" in res or "permissionDecision" in res or "exit code 2" in res
        if is_block:
            gating_blocks.append({"tool": c.get("name", ""), "evidence": head[:200]})
        elif _ERROR_MARKERS.search(head):
            failures.append({
                "tool": c.get("name", ""),
                "input": json.dumps(c.get("input", {}))[:160],
                "evidence": head[:200],
            })
        if _AUTH_MARKERS.search(head):
            auth_hits.append({"tool": c.get("name", ""), "evidence": head[:200]})

    # Retry loops: a tool name that appears again after one of its calls failed.
    failed_tools = [f["tool"] for f in failures]
    seq = [c.get("name", "") for c in calls]
    retries = sorted({t for t in failed_tools if seq.count(t) > 1})

    # Checklist gaps: expected steps with no marker anywhere in tool inputs/assistant text.
    haystack = asst_text + "\n" + "\n".join(
        f"{c.get('name','')} {json.dumps(c.get('input',{}))}" for c in calls
    ).lower()
    missing_steps = [
        label for label, markers in steps
        if not any(re.search(m, haystack) for m in markers)
    ]

    return {
        "session_id": transcript_path.stem,
        "path": str(transcript_path),
        "n_tool_calls": len(calls),
        "failures": failures,
        "gating_blocks": gating_blocks,
        "auth_friction": auth_hits,
        "retry_loops": retries,
        "checklist_gaps": missing_steps,
    }


def build_review_prompt(repo: Path, corpus: list[dict]) -> str:
    """Assemble the friction corpus + agent identity into an evaluator–optimizer prompt."""
    persona = ""
    pp = repo / "persona.md"
    if pp.exists():
        persona = pp.read_text()[:1500]
    return (
        "You are canopy's agent self-improvement reviewer. Below is structural friction extracted "
        f"from recent TURNS of the agent at {repo} (its own git repo).\n\n"
        f"AGENT PERSONA (excerpt):\n{persona}\n\n"
        f"FRICTION CORPUS (deterministic signals per turn):\n{json.dumps(corpus, indent=2)}\n\n"
        "Produce a YAML list of findings. Each item:\n"
        "  - title: short imperative\n"
        f"  - friction_type: one of {list(FRICTION_TYPES)}\n"
        "  - evidence: what in the corpus supports it\n"
        "  - fix_kind: one of [skill_edit, hook_rule, claude_update, channel_fix, new_skill]\n"
        "  - target: the file/path in the agent repo the fix touches\n"
        "  - recommendation: the concrete change to make\n"
        "  - confidence: high|medium|low\n"
        "Rules: prefer hook_rule for any 'never do X' invariant (not prose); prefer new_skill/"
        "skill_edit when a manual multi-step pattern repeats; only include findings with real "
        "evidence in the corpus. Output ONLY the YAML list.\n"
    )


def parse_findings(output: str) -> list[dict]:
    import yaml
    text = output.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.split("\n") if not l.strip().startswith("```"))
    try:
        result = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    return result if isinstance(result, list) else []


def run_review(
    slug_or_path: str,
    *,
    hours: int = 168,
    use_llm: bool = True,
    model: str = "sonnet",
    max_budget_usd: float = 0.50,
    projects_dir: Path = CLAUDE_PROJECTS,
) -> dict:
    """Review an agent's recent turns. Returns {agent, repo, turns, signals, findings, error?}."""
    repo = resolve_agent_repo(slug_or_path)
    if not repo or not repo.exists():
        return {"error": f"could not resolve agent repo for {slug_or_path!r}"}

    transcripts = find_turn_transcripts(repo, hours=hours, projects_dir=projects_dir)
    corpus = [friction_signals(t) for t in transcripts]
    result = {
        "agent": repo.name,
        "repo": str(repo),
        "turns": len(corpus),
        "signals": corpus,
        "findings": [],
    }
    if not corpus or not use_llm:
        return result

    prompt = build_review_prompt(repo, corpus)
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--model", model,
             "--max-budget-usd", str(max_budget_usd), "--no-session-persistence"],
            capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired:
        result["error"] = "claude -p timed out"
        return result
    if proc.returncode == 0:
        result["findings"] = parse_findings(proc.stdout)
    else:
        result["error"] = f"claude -p failed: {proc.stderr.strip()[:200]}"
    return result
