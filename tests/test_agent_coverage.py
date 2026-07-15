"""Tests for `canopy agent coverage` — bring-up lens (declared surface vs. actual firing)."""
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.agent_coverage import (
    _parse_ts,
    compute_bursts,
    evidence_from_entries,
    scan_evidence,
)

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _ts(day, hour=9, sid="s1"):
    return (datetime(2026, 7, day, hour, 0, 0, tzinfo=timezone.utc), sid)


def _assistant(content, ts="2026-07-09T09:00:00Z"):
    return {"type": "assistant", "timestamp": ts, "message": {"content": content}}


def _user_text(text, ts="2026-07-09T09:00:00Z"):
    return {"type": "user", "timestamp": ts,
            "message": {"content": [{"type": "text", "text": text}]}}


def test_compute_bursts_merges_consecutive_days_and_splits_on_gap():
    # The real eva timeline: 07-01,02 | (6 dark days) | 07-09,10 | (2 dark) | 07-13,14,15
    stamps = [
        _ts(1, sid="a"), _ts(2, sid="b"),
        _ts(9, sid="c"), _ts(10, sid="d"),
        _ts(13, sid="e"), _ts(14, sid="f"), _ts(15, sid="g"),
    ]
    bursts = compute_bursts(stamps, gap_days=2)
    assert [(b["id"], b["start"], b["end"], b["active_days"]) for b in bursts] == [
        (1, "2026-07-01", "2026-07-02", 2),
        (2, "2026-07-09", "2026-07-10", 2),
        (3, "2026-07-13", "2026-07-15", 3),
    ]


def test_compute_bursts_counts_distinct_sessions():
    stamps = [_ts(1, 9, "a"), _ts(1, 10, "a"), _ts(1, 11, "b"), _ts(2, 9, "b")]
    bursts = compute_bursts(stamps, gap_days=2)
    assert len(bursts) == 1
    assert bursts[0]["sessions"] == 2  # a, b — not 4 entries
    assert bursts[0]["active_days"] == 2


def test_compute_bursts_gap_boundary_is_inclusive():
    # gap_days=2 means: a >=2-day gap splits. 07-01 -> 07-02 is contiguous (gap 1).
    assert len(compute_bursts([_ts(1), _ts(2)], gap_days=2)) == 1
    # 07-01 -> 07-03 is a 2-day gap: splits.
    assert len(compute_bursts([_ts(1), _ts(3)], gap_days=2)) == 2


def test_compute_bursts_empty():
    assert compute_bursts([], gap_days=2) == []


def test_evidence_counts_skill_tool_call():
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "eva:lead-outreach"}}])]
    ev = evidence_from_entries(entries, "eva", ["lead-outreach"])
    assert len(ev["lead-outreach"]) == 1
    assert ev["lead-outreach"][0]["kind"] == "skill_tool_call"


def test_evidence_counts_skill_md_read():
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/Users/j/emdash/repositories/eva/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1
    assert ev["turn"][0]["kind"] == "skill_md_read"


def test_evidence_counts_slash_invocation_in_text():
    entries = [_user_text("go do /eva:turn now please")]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev["turn"][0]["kind"] == "slash_invocation"


def test_bare_mention_in_tool_result_is_not_evidence():
    """THE false-positive guard: `ls skills/` output and git diffs must not count."""
    entries = [
        {"type": "user", "timestamp": "2026-07-09T09:00:00Z", "message": {"content": [
            {"type": "tool_result",
             "content": "skills/cea-botec/SKILL.md\nskills/reviewer/SKILL.md"}]}},
        {"type": "user", "timestamp": "2026-07-09T09:00:00Z", "message": {"content": [
            {"type": "tool_result",
             "content": "diff --git a/skills/cea-botec/SKILL.md b/skills/cea-botec/SKILL.md"}]}},
    ]
    ev = evidence_from_entries(entries, "eva", ["cea-botec", "reviewer"])
    assert ev == {}


def test_evidence_does_not_confuse_similar_skill_names():
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/x/eva/skills/turn-review/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn", "turn-review"])
    assert "turn" not in ev
    assert len(ev["turn-review"]) == 1


def test_scan_evidence_tags_transcript_path():
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "eva:turn"}}])]
    ev = scan_evidence([Path("/tmp/a.jsonl")], "eva", ["turn"], reader=lambda p: entries)
    assert ev["turn"][0]["transcript"] == "/tmp/a.jsonl"


# --- FINDING 1: cross-agent false "live" ------------------------------------

def test_skill_md_read_matches_owning_agent_repo_layout():
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/Users/j/emdash/repositories/eva/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


def test_skill_md_read_matches_owning_agent_worktree_layout():
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path":
                   "/Users/j/emdash/worktrees/eva/emdash/feat-x/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


def test_skill_md_read_does_not_match_foreign_agent_path():
    """eva's transcript reading ace's turn skill must NOT count as eva's turn firing."""
    entries = [_assistant([
        {"type": "tool_use", "name": "Read",
         "input": {"file_path": "/Users/j/emdash/repositories/ace/skills/turn/SKILL.md"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev == {}


def test_skill_tool_call_accepts_bare_skill_name():
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "turn"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


def test_skill_tool_call_accepts_own_namespace():
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "eva:turn"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert len(ev["turn"]) == 1


def test_skill_tool_call_rejects_foreign_namespace():
    """A Skill call with input.skill='ace:turn' must not count as eva's turn firing."""
    entries = [_assistant([
        {"type": "tool_use", "name": "Skill", "input": {"skill": "ace:turn"}}])]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev == {}


# --- FINDING 2: _parse_ts must return aware datetimes -----------------------

def test_parse_ts_naive_string_returns_aware_datetime():
    dt = _parse_ts("2026-07-09T09:00:00")
    assert dt is not None
    assert dt.tzinfo is not None


def test_parse_ts_z_suffixed_string_stays_utc_and_unchanged():
    dt = _parse_ts("2026-07-09T09:00:00Z")
    assert dt == datetime(2026, 7, 9, 9, 0, 0, tzinfo=timezone.utc)


# --- FINDING 3: unparseable timestamp must not produce ts=None evidence -----

def test_entry_with_unparseable_timestamp_yields_no_evidence():
    entries = [_assistant(
        [{"type": "tool_use", "name": "Skill", "input": {"skill": "turn"}}],
        ts="not-a-timestamp",
    )]
    ev = evidence_from_entries(entries, "eva", ["turn"])
    assert ev == {}
