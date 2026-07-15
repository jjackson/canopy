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
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def evidence_from_entries(entries: list[dict], slug: str,
                          skill_names: list[str]) -> dict[str, list[dict]]:
    """Invocation-shaped evidence per skill, from ONE transcript's entries.

    Only ``tool_use`` inputs and ``text`` blocks are scanned. ``tool_result`` content
    is deliberately NOT scanned: `ls skills/` listings and git diffs live there, and
    counting them would mark never-run skills as live. A mention is not an invocation.
    """
    md_res = {n: re.compile(rf"/skills/{re.escape(n)}/SKILL\.md$") for n in skill_names}
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
        for c in content:
            if not isinstance(c, dict):
                continue
            ctype = c.get("type")
            if ctype == "tool_use":
                inp = c.get("input") or {}
                name = c.get("name")
                if name == "Skill":
                    ref = str(inp.get("skill") or "")
                    bare = ref.split(":")[-1]
                    if bare in md_res:
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
