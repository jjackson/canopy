"""Tests for `canopy agent coverage` — bring-up lens (declared surface vs. actual firing)."""
from datetime import datetime, timezone

from orchestrator.agent_coverage import compute_bursts

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def _ts(day, hour=9, sid="s1"):
    return (datetime(2026, 7, day, hour, 0, 0, tzinfo=timezone.utc), sid)


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
