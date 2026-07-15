"""Per-AGENT bring-up coverage — `canopy agent coverage`.

`canopy agent health` answers "is this agent's workload healthy for its NEXT turn"
(board + inbox, point-in-time). THIS module answers a longitudinal question: "how
much of what we said this agent would be is actually LIVE yet" — which declared
skills have ever fired, which fired and then stopped, and which never fired despite
having the chance.

The fleet is in bring-up, not maintenance: things are built and exercised inside
short bursts (1-2 active days separated by ~6 dark days), then decay when they
can't quite be made to work. So OPPORTUNITY IS COUNTED IN BURSTS SURVIVED, never in
wall-clock days -- a day-based age gate spans whole bursts and suppresses exactly
the most interesting skills. A trough is not a finding: an agent with no bursts
since a skill was written yields no finding at all.

Facts and deterministic buckets only -- WHY a skill never fired (blocked? forgotten?
premature?) is the caller's job (Ada's fleet-persona-coverage skill judges; this
module never does). Read-only by construction: writes to no repo, mailbox, board, or
turn queue.

Same shape as agent_health.py: small probes with injectable dependencies (``call``
for canopy-web, ``now``, ``projects_dir``), composed by ``run_agent_coverage``.
"""
from __future__ import annotations

import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from orchestrator.transcripts import read_transcript


def compute_bursts(stamps: list[tuple[datetime, str]], gap_days: int = 2) -> list[dict]:
    """Group activity timestamps into bursts of contiguous active days.

    A burst is a run of active days separated by a gap of >= ``gap_days``. This is
    the unit of OPPORTUNITY: "did this skill have a chance to fire?" is answered in
    bursts, not days.
    """
    if not stamps:
        return []
    # date -> set of session ids active that day
    by_day: dict[object, set] = {}
    for ts, sid in stamps:
        by_day.setdefault(ts.date(), set()).add(sid)

    days = sorted(by_day)
    groups: list[list] = [[days[0]]]
    for prev, day in zip(days, days[1:]):
        if (day - prev) >= timedelta(days=gap_days):
            groups.append([day])
        else:
            groups[-1].append(day)

    out = []
    for i, group in enumerate(groups, start=1):
        sessions = set()
        for d in group:
            sessions |= by_day[d]
        out.append({
            "id": i,
            "start": group[0].isoformat(),
            "end": group[-1].isoformat(),
            "active_days": len(group),
            "sessions": len(sessions),
        })
    return out


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    # Mirror agent_health._parse_when: attach the local zone to naive timestamps so
    # every evidence ts is aware -- mixing naive/aware here would shift the `.date()`
    # burst boundaries downstream.
    return dt.astimezone() if dt.tzinfo is None else dt


def evidence_from_entries(entries: list[dict], slug: str,
                          skill_names: list[str]) -> dict[str, list[dict]]:
    """Invocation-shaped evidence per skill, from ONE transcript's entries.

    Only ``tool_use`` inputs and ``text`` blocks are scanned. ``tool_result`` content
    is deliberately NOT scanned: `ls skills/` listings and git diffs live there, and
    counting them would mark never-run skills as live. A mention is not an invocation.
    """
    # Require the read path to belong to THIS agent: slug must appear DIRECTLY under
    # repositories/ or worktrees/ before the skills/ segment (repo layout:
    # /repositories/<slug>/skills/..., worktree layout:
    # /worktrees/<slug>/<branch>/skills/... or /worktrees/<slug>/emdash/<branch>/skills/...).
    # Without this, coincidental `/eva/` in fixture paths (e.g. test fixtures) or
    # cross-agent reads of a sibling's identically-named skill file falsely count as THIS
    # agent's skill firing.
    md_res = {n: re.compile(
        rf"/(?:repositories|worktrees)/{re.escape(slug)}/(?:.*/)?skills/{re.escape(n)}/SKILL\.md$"
    ) for n in skill_names}
    slash_res = {n: re.compile(rf"/{re.escape(slug)}:{re.escape(n)}(?![\w-])")
                 for n in skill_names}
    out: dict[str, list[dict]] = {}

    def add(name, ts, kind, line):
        out.setdefault(name, []).append({"ts": ts, "kind": kind, "line": line})

    for entry in entries:
        content = (entry.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        ts = _parse_ts(entry.get("timestamp"))
        if ts is None:
            # Can't place this invocation on the burst timeline -- unusable as
            # evidence rather than a landmine `ts: None` for downstream `.date()`.
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            ctype = c.get("type")
            if ctype == "tool_use":
                inp = c.get("input") or {}
                name = c.get("name")
                if name == "Skill":
                    ref = str(inp.get("skill") or "")
                    ns, sep, bare = ref.partition(":")
                    if not sep:
                        ns, bare = None, ref
                    # Bare skill name, or namespaced to THIS agent -- reject a
                    # foreign namespace (e.g. "ace:turn" while scanning eva).
                    if bare in md_res and (ns is None or ns == slug):
                        add(bare, ts, "skill_tool_call", ref)
                elif name == "Read":
                    fp = str(inp.get("file_path") or "")
                    for n, rx in md_res.items():
                        if rx.search(fp):
                            add(n, ts, "skill_md_read", fp)
            elif ctype == "text":
                text = str(c.get("text") or "")
                for n, rx in slash_res.items():
                    if rx.search(text):
                        add(n, ts, "slash_invocation", f"/{slug}:{n}")
            # ctype == "tool_result" -> intentionally skipped (see docstring)
    return out


def scan_evidence(paths: list[Path], slug: str, skill_names: list[str], *,
                  reader: Callable = read_transcript) -> dict[str, list[dict]]:
    """Invocation evidence per skill across a transcript corpus."""
    out: dict[str, list[dict]] = {}
    for p in paths:
        found = evidence_from_entries(reader(p), slug, skill_names)
        for name, evs in found.items():
            for e in evs:
                out.setdefault(name, []).append({**e, "transcript": str(p)})
    return out


SUB_SKILL_SUFFIXES = ("-eval", "-qa")


def declared_skills(repo: Path) -> list[str]:
    """Skill names declared in the repo (a dir under skills/ holding a SKILL.md)."""
    root = repo / "skills"
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if (d / "SKILL.md").is_file())


def parent_of(name: str, all_names: set[str]) -> Optional[str]:
    """The parent skill for an `-eval`/`-qa` sub-skill, else None.

    Sub-skills are invoked BY their parent, not independently -- judging them
    separately turns ace's 128 skills into a 79-item noise list.
    """
    for suffix in SUB_SKILL_SUFFIXES:
        if name.endswith(suffix):
            parent = name[: -len(suffix)]
            if parent in all_names:
                return parent
    return None


def persona_info(repo: Path) -> dict:
    """persona.md presence/size. Absent is a FACT (echo has none), not an error."""
    p = repo / "persona.md"
    if not p.is_file():
        return {"present": False, "path": None, "bytes": 0}
    return {"present": True, "path": "persona.md", "bytes": p.stat().st_size}


def _git(repo: Path, args: list[str], runner) -> str:
    try:
        r = runner(["git", "-C", str(repo), *args],
                   capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def skill_git_facts(repo: Path, name: str, now: datetime, *,
                    runner=subprocess.run) -> dict:
    """When a skill landed, when it was last touched, how often -- from git.

    `commits`/`last_touched_days` are CONTEXT (a skill edited yesterday that never
    fired is a sharper story), never a bucket: buckets are firing behavior.
    """
    path = f"skills/{name}/SKILL.md"
    added = _git(repo, ["log", "--diff-filter=A", "--format=%aI", "--", path], runner)
    last = _git(repo, ["log", "-1", "--format=%aI", "--", path], runner)
    log = _git(repo, ["log", "--format=%H", "--", path], runner)
    if not added:
        return {"added_at": None, "age_days": None,
                "last_touched_days": None, "commits": 0}
    added_at = added.splitlines()[-1]  # last line = earliest = the adding commit

    def age(v):
        dt = _parse_ts(v)
        return None if dt is None else round((now - dt).total_seconds() / 86400.0, 1)

    return {"added_at": added_at, "age_days": age(added_at),
            "last_touched_days": age(last), "commits": len(log.splitlines())}
