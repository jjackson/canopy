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
    extract_user_messages,
    read_transcript,
)

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

# Operating-model friction taxonomy. Findings get tagged with one of these.
FRICTION_TYPES = (
    "human_correction",  # the human had to correct/override the agent (HIGHEST signal — read these first)
    "tool_failure",    # a tool call errored
    "retry_loop",      # the same tool was re-tried after a failure
    "gating_block",    # a PreToolUse hook blocked an action (deny)
    "checklist_gap",   # an expected turn step never ran
    "skill_capture",   # a multi-step manual pattern that should be a skill
    "auth_friction",   # auth/credential/setup blockers
)

# Human-correction mining — the lens agent-review was BLIND to (echo's last turn taught us: it
# flagged git pathspec errors but missed Jonathan demanding "NEVER EVER submit without review").
# A human overriding a safety behavior, or expressing confusion, outranks any mechanical friction.
_CORRECTION_PATTERNS = (
    # safety override — the agent did (or was about to do) something it must NOT do autonomously
    ("safety_override", re.compile(
        r"\bnever\b.{0,40}\b(submit|send|post|publish|delete|push|merge|pay|buy|email|reply)\b|"
        r"without (?:human |explicit )?(?:review|approval|sign-?off|permission)|"
        r"\bmust not\b|\bshould never\b|\bdo ?n['’o]?t ever\b|\bnever ever\b", re.I)),
    # confusion — the agent's output didn't make sense to the human
    ("confusion", re.compile(
        r"\bi['’ ]?m lost\b|\bi am lost\b|\bconfus|why are you|why did you|what are you doing|"
        r"that['’]s not what i|does ?n['’]t make sense|makes no sense|i don['’]t (?:get|follow|understand)", re.I)),
    # strong correction — a forceful "no, do it differently"
    ("strong_correction", re.compile(
        r"\bstop\b|\byou['’]re wrong\b|that['’]s wrong|that is wrong|^\s*no[,.! ]|"
        r"\binstead of\b|not what i (?:asked|wanted|meant)|\bredo\b|\bundo\b", re.I)),
)


def human_corrections(entries: list[dict]) -> list[dict]:
    """Mine the HUMAN side of a turn for corrections/overrides/confusion — the highest-signal
    friction. A forceful safety correction ("NEVER submit without review") matters more than ten
    git errors, but the mechanical signals miss it entirely. Returns [{kinds, quote}]."""
    out: list[dict] = []
    for m in extract_user_messages(entries):
        s = (m or "").strip()
        if not s:
            continue
        kinds = [kind for kind, pat in _CORRECTION_PATTERNS if pat.search(s)]
        # ALL-CAPS emphasis (2+ shouted words, or NEVER/ALWAYS/STOP) = a forceful demand
        if re.search(r"\b[A-Z]{3,}\b[^a-z]{0,30}\b[A-Z]{3,}\b", s) or re.search(
                r"\b(NEVER|ALWAYS|STOP|DO NOT|MUST)\b", s):
            kinds.append("emphasis")
        if kinds:
            out.append({"kinds": sorted(set(kinds)), "quote": s.replace("\n", " ")[:240]})
    return out

# Expected turn steps for an operating-model agent, with markers that evidence each ran.
# A step with no marker present in a turn is a candidate `checklist_gap`.
DEFAULT_TURN_STEPS = (
    ("preflight", (r"preflight", r"readiness")),
    ("self-review", (r"self-review", r"self review")),
    ("skill-self-check", (r"skill.?self.?check", r"did i (create|improve) a skill",
                          r"should be a skill")),
    ("workspace-refresh", (r"agent-publish", r"/agents/")),
)

# NOTE: no bare "blocked" here — PR status output ("mergeable: MERGEABLE/BLOCKED") and prose
# ("blocked only on required review") made every PR-triage turn look like a failure storm.
# Gating friction is detected separately via _GATING_MARKERS.
_ERROR_MARKERS = re.compile(
    r"(?:^|\b)(?:error|errno|traceback|exception|failed|not found|not been used|"
    r"permission denied|fatal|✗|exit code [1-9]|"
    r"4(?:00|01|03|04|09|22|29)|5(?:00|02|03))\b",
    re.I,
)
# A gating block is a PreToolUse hook outcome — only tools the guard actually gates can
# produce one (a Read of the hook's own source contains "permissionDecision" but is not a block).
# When a hook fires, its message IS the whole tool result, so the marker sits at the head —
# a `cat config/gating.json` carries the same strings, but buried past the file preamble.
_GATABLE_TOOLS = {"Bash", "Edit", "Write", "NotebookEdit"}
_GATING_HEAD = 300
# No bare "PreToolUse" here — gating-policy prose mentions it constantly; hook RESULTS
# always carry one of these instead.
_GATING_MARKERS = re.compile(
    r"hookSpecificOutput|permissionDecision|BLOCKED:|hook (?:denied|blocked)|blocked by .{0,20}hook",
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


def _call_subject(call: dict) -> str:
    """The most comparable piece of a call's input — command / path, else the whole input."""
    inp = call.get("input")
    if not isinstance(inp, dict):
        return str(inp or "")
    return str(
        inp.get("command")
        or inp.get("file_path")
        or inp.get("notebook_path")
        or json.dumps(inp, sort_keys=True)
    )


def _retried_after(calls: list[dict], i: int, window: int = 8) -> bool:
    """True if the tool that failed at index i re-ran shortly after on a near-identical
    subject. (The old check — same tool name appearing anywhere else in the turn — flagged
    every Bash-heavy turn as a retry loop.)"""
    tool = calls[i].get("name", "")
    prefix = _call_subject(calls[i]).strip()[:30]
    if not prefix:
        return False
    for later in calls[i + 1 : i + 1 + window]:
        if later.get("name") != tool:
            continue
        other = _call_subject(later).strip()[:30]
        if other and (other.startswith(prefix) or prefix.startswith(other)):
            return True
    return False


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
    failed_idx: list[int] = []
    for i, c in enumerate(calls):
        res = _result_text(c)
        if not res:
            continue
        head = res[:600]
        tool = c.get("name", "")
        if tool in _GATABLE_TOOLS and _GATING_MARKERS.search(res[:_GATING_HEAD]):
            gating_blocks.append({"tool": tool, "evidence": head[:200]})
        elif _ERROR_MARKERS.search(head):
            failed_idx.append(i)
            failures.append({
                "tool": tool,
                "input": json.dumps(c.get("input", {}))[:160],
                "evidence": head[:200],
            })
        if _AUTH_MARKERS.search(head):
            auth_hits.append({"tool": tool, "evidence": head[:200]})

    # Retry loops: the same tool re-run on a near-identical subject shortly after failing.
    retries = sorted({calls[i].get("name", "") for i in failed_idx if _retried_after(calls, i)})

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
        "human_corrections": human_corrections(entries),   # HIGHEST-signal — read first
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
        "Rules:\n"
        "- `human_corrections` are the HIGHEST-signal items in the corpus — a human overriding a "
        "safety behavior (e.g. 'NEVER submit without review') or expressing confusion ('I'm lost') "
        "matters MORE than any tool failure. Surface those findings FIRST, mark them high confidence, "
        "and turn a `safety_override` into a hard invariant (hook_rule), never just prose guidance.\n"
        "- A `confusion` correction means the agent's turn structure/communication failed — recommend "
        "a skill_edit that fixes how it presents (e.g. decide-then-show, not ask-then-show-something-else).\n"
        "- prefer hook_rule for any 'never do X' invariant; prefer new_skill/skill_edit when a manual "
        "multi-step pattern repeats; only include findings with real evidence in the corpus.\n"
        "Output ONLY the YAML list.\n"
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
