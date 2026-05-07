"""Skill description budget arithmetic.

Claude Code surfaces every installed skill's `description` field in the
system prompt at session start. Each skill is allotted a soft per-skill
budget; the aggregated descriptions across all skills are also capped.
When either limit is exceeded, descriptions are truncated or whole
skills are silently dropped — operators have no visibility into which.

This module provides the deterministic budget logic used by:
- `canopy skills budget` — ranked size table + aggregate gauge
- `canopy skills dropped` — simulate which skills get dropped under the cap

The defaults match the limits surfaced by Claude Code as of canopy
v0.2.80. They're configurable via CLI flags so the same module survives
limit changes without a code edit.
"""
from __future__ import annotations

from typing import Iterable

# Per-skill description char budget. Descriptions over this are truncated
# but the skill itself still ships. The recommended maximum from Anthropic's
# skill-authoring guidance is 1024 chars; we keep the same threshold.
# Override with `--per-skill-limit` if Claude Code's actual cap shifts.
DEFAULT_PER_SKILL_LIMIT = 1024

# Aggregate char budget across all skill descriptions. Once exceeded,
# subsequent skills are dropped wholesale. The exact cap is not publicly
# documented; the finding that motivated this command was triggered by an
# operator seeing "142 dropped" with the assumed cap at ~1500. We default
# to that value here so the gauge is calibrated for the case the command
# was built for; pass `--aggregate-limit` to recalibrate.
DEFAULT_AGGREGATE_LIMIT = 1500


def measure(entry: dict) -> int:
    """Return the description size for budget purposes.

    Trailing whitespace is stripped before counting.
    """
    desc = (entry.get("description") or "").strip()
    return len(desc)


def per_skill_status(size: int, per_skill_limit: int = DEFAULT_PER_SKILL_LIMIT) -> str:
    """Classify a single skill's description size against the per-skill cap.

    - "OK"   — within budget
    - "WARN" — within budget but >80% of cap (close to truncation)
    - "OVER" — exceeds cap (will be truncated by the harness)
    """
    if size > per_skill_limit:
        return "OVER"
    if size > int(per_skill_limit * 0.8):
        return "WARN"
    return "OK"


def rank(entries: Iterable[dict]) -> list[dict]:
    """Sort entries by description size descending, ties broken by qualified name.

    Returns new dicts augmented with `description_size` and `per_skill_status`.
    """
    out: list[dict] = []
    for e in entries:
        size = measure(e)
        out.append({
            **e,
            "description_size": size,
            "per_skill_status": per_skill_status(size),
        })
    out.sort(key=lambda e: (-e["description_size"], e.get("qualified", "")))
    return out


def simulate_drops(
    entries: Iterable[dict],
    per_skill_limit: int = DEFAULT_PER_SKILL_LIMIT,
    aggregate_limit: int = DEFAULT_AGGREGATE_LIMIT,
) -> dict:
    """Simulate Claude Code's drop logic against the configured limits.

    Algorithm (matches Claude Code's documented behavior as of v0.2.80):
    1. For each skill, the per-skill cap truncates its description to
       `per_skill_limit` chars; the truncated length is what counts toward
       the aggregate.
    2. Skills are ordered by `qualified` (stable, deterministic) and
       summed in order. Once the running total would exceed
       `aggregate_limit`, subsequent skills are flagged `dropped`.

    Returns:
        {
            "kept":    [<entry>, ...]   # skills that ship in the system prompt
            "dropped": [<entry>, ...]   # skills dropped due to aggregate cap
            "totals": {
                "skills_total":      N,
                "kept_count":        K,
                "dropped_count":     D,
                "aggregate_used":    bytes counted toward aggregate,
                "aggregate_limit":   the cap,
                "per_skill_limit":   the per-skill cap,
                "per_skill_over":    count of skills whose raw size exceeds per-skill cap,
            }
        }
    """
    materialized = sorted(entries, key=lambda e: e.get("qualified", ""))
    kept: list[dict] = []
    dropped: list[dict] = []
    used = 0
    per_skill_over = 0
    for e in materialized:
        raw_size = measure(e)
        capped = min(raw_size, per_skill_limit)
        if raw_size > per_skill_limit:
            per_skill_over += 1
        proposed = used + capped
        annotated = {
            **e,
            "description_size": raw_size,
            "capped_size": capped,
            "per_skill_status": per_skill_status(raw_size, per_skill_limit),
        }
        if proposed > aggregate_limit:
            annotated["drop_reason"] = "aggregate_limit_exceeded"
            dropped.append(annotated)
            continue
        used = proposed
        kept.append(annotated)
    return {
        "kept": kept,
        "dropped": dropped,
        "totals": {
            "skills_total": len(materialized),
            "kept_count": len(kept),
            "dropped_count": len(dropped),
            "aggregate_used": used,
            "aggregate_limit": aggregate_limit,
            "per_skill_limit": per_skill_limit,
            "per_skill_over": per_skill_over,
        },
    }
