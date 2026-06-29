"""Unit tests for the deterministic core of the render pacing audit.

The ffmpeg-backed detectors (silence/freeze) are integration-tested by running
on a real video; here we lock the pure interval math + the run-report bug parse,
which is what classifies a region as dead-air / silent-motion / recording-bug.
"""
from __future__ import annotations

import json

from scripts.ddd.render_pacing_audit import _intersect, _merge, _subtract, recording_bugs


def test_merge_overlapping_and_adjacent():
    assert _merge([(0.0, 2.0), (1.0, 3.0), (5.0, 6.0)]) == [(0.0, 3.0), (5.0, 6.0)]
    assert _merge([]) == []


def test_intersect_silence_and_freeze():
    # silence [0,5] ∩ freeze {[2,3],[4,7]} = dead-air [2,3],[4,5]
    assert _intersect([(0.0, 5.0)], [(2.0, 3.0), (4.0, 7.0)]) == [(2.0, 3.0), (4.0, 5.0)]
    assert _intersect([(0.0, 1.0)], [(2.0, 3.0)]) == []


def test_subtract_silence_minus_freeze_is_silent_motion():
    # silence [0,10] minus freeze {[2,3],[5,6]} = silent-motion [0,2],[3,5],[6,10]
    assert _subtract([(0.0, 10.0)], [(2.0, 3.0), (5.0, 6.0)]) == [(0.0, 2.0), (3.0, 5.0), (6.0, 10.0)]
    assert _subtract([(0.0, 5.0)], []) == [(0.0, 5.0)]


def test_recording_bugs_flags_failed_and_timeout(tmp_path):
    report = {
        "actions": [
            {"kind": "click", "target": "Filter", "ok": True, "scene_index": 1},
            {"kind": "click", "target": "Award response", "ok": False,
             "error_kind": "target_not_found", "must_succeed": True, "scene_index": 4},
            {"kind": "wait_for", "target": "Get Feedback Again", "ok": False,
             "error_kind": "timeout", "scene_index": 5},
        ]
    }
    p = tmp_path / "run-report.json"
    p.write_text(json.dumps(report))
    bugs = recording_bugs(str(p))
    assert len(bugs) == 2  # the ok:True click is not a bug
    assert "scene 4" in bugs[0] and "must_succeed" in bugs[0] and "target_not_found" in bugs[0]
    assert "scene 5" in bugs[1] and "timeout" in bugs[1]


def test_recording_bugs_clean_and_missing():
    assert recording_bugs(None) == []
    assert recording_bugs("/nonexistent/run-report.json") == []
