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

from datetime import datetime, timedelta


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
