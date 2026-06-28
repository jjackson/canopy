"""Tests for pace-aware de-dwelling in scripts.ddd.snippets.

The de-dweller collapses long dead-air gaps (no on-screen motion) down to a
brief ``dwell``, to trim wait/hold/snapshot dead time. That is WRONG for a
``pace: teach`` scene, which deliberately holds on a highlighted table/column
for ~8-15s while the voiceover explains it — those held frames carry the
narration. So:

  * ``pace: flow`` / default-None scenes → de-dwelled (current behavior, the
    long gap collapses to ``dwell``).
  * ``pace: teach`` scenes → KEPT (full scene footage retained, not collapsed).

The ffmpeg scene-change detection is monkeypatched so the test is hermetic
(no clip, no ffmpeg) and exercises only the collapse-vs-keep decision.
"""
from __future__ import annotations

import pytest

from scripts.ddd import snippets


# A motion profile with a long DEAD span: motion at t=0..1, then nothing until
# t=20 (a 19s gap >> gap_max=6), then motion to t=21. A 22s scene window.
_START = 100.0
_DUR = 22.0
_MOTION_TIMES = [0.2, 0.6, 1.0, 20.0, 20.5, 21.0]


@pytest.fixture
def _fake_motion(monkeypatch):
    """Stub the ffmpeg scene-change detector with a fixed motion profile."""
    monkeypatch.setattr(
        snippets,
        "_scene_change_times",
        lambda clip_path, start, dur, threshold: list(_MOTION_TIMES),
    )


def _total(segments: list[tuple[float, float]]) -> float:
    return round(sum(d for _, d in segments), 3)


def test_default_scene_collapses_long_gap(_fake_motion):
    """A >gap_max dead span in a DEFAULT/flow scene collapses to ~dwell.

    The kept footage is the two motion clusters (~1s + ~1s) plus the single
    collapsed ``dwell`` beat — far less than the original 22s.
    """
    segs = snippets.dedwell_segments("clip.mp4", _START, _DUR)  # keep_dwell defaults False
    total = _total(segs)
    assert total < _DUR / 2, f"expected the dead span collapsed, kept {total}s of {_DUR}s"
    # The 19s gap must NOT survive as a single 19s segment.
    assert max(d for _, d in segs) < 5.0


def test_teach_scene_keeps_full_footage(_fake_motion):
    """The SAME span in a teach scene (keep_dwell=True) is kept intact."""
    segs = snippets.dedwell_segments("clip.mp4", _START, _DUR, keep_dwell=True)
    assert segs == [(round(_START, 3), round(_DUR, 3))]
    assert _total(segs) == pytest.approx(_DUR)


def test_keep_dwell_preserves_full_range_even_with_motion(_fake_motion):
    """keep_dwell short-circuits BEFORE motion detection — full range, one segment."""
    segs = snippets.dedwell_segments("clip.mp4", _START, _DUR, keep_dwell=True)
    assert len(segs) == 1
    assert segs[0] == (round(_START, 3), round(_DUR, 3))


# ---------------------------------------------------------------------------
# Caller-level: build_snippets threads scene.pace into the de-dwell decision.
# ---------------------------------------------------------------------------


def _report():
    return {"scenes": [{"scene_index": 1, "start_seconds": _START, "duration_seconds": _DUR}]}


def _spec(pace):
    scene = {"title": "Teach the table", "concept_claim": "x", "narrative": "narrate"}
    if pace is not None:
        scene["pace"] = pace
    return {"scenes": [scene]}


@pytest.fixture
def _local_clip(monkeypatch, tmp_path):
    """Make build_snippets treat a path as a present local clip (no real ffmpeg)."""
    clip = tmp_path / "master.mp4"
    clip.write_bytes(b"\x00")
    return str(clip)


def _build(pace, clip, monkeypatch):
    monkeypatch.setattr(
        snippets,
        "_scene_change_times",
        lambda clip_path, start, dur, threshold: list(_MOTION_TIMES),
    )
    return snippets.build_snippets(
        narrative_slug="demo",
        spec=_spec(pace),
        report=_report(),
        source_clip_local=clip,
        source_clip_hosted=None,
    )


@pytest.mark.parametrize("pace", ["flow", None])
def test_build_snippets_flow_or_default_dedwells(pace, _local_clip, monkeypatch):
    """flow AND default(None) are de-dwelled — only an explicit teach keeps footage."""
    snips = _build(pace, _local_clip, monkeypatch)
    assert snips[0]["duration_seconds"] < _DUR / 2


def test_build_snippets_teach_keeps_footage(_local_clip, monkeypatch):
    """Only an explicit pace:teach keeps the full footage (holds carry the narration)."""
    snips = _build("teach", _local_clip, monkeypatch)
    assert snips[0]["duration_seconds"] == pytest.approx(_DUR)
    assert snips[0]["segments"] == [{"start_seconds": _START, "duration_seconds": _DUR}]


# ---------------------------------------------------------------------------
# Ground-truth loading-wait excision (recorder-driven, not pixel-based).
# ---------------------------------------------------------------------------


def test_excise_span_splits_a_segment():
    # one seg covering master [100,135]; cut [113,125] → two segments
    assert snippets._excise_span_from_segs([(100.0, 35.0)], 113.0, 125.0) == [
        (100.0, 13.0),
        (125.0, 10.0),
    ]


def test_excise_span_no_overlap_keeps_seg():
    assert snippets._excise_span_from_segs([(100.0, 10.0)], 200.0, 210.0) == [(100.0, 10.0)]


def test_excise_span_across_two_segments():
    # segs master [0,10] + [200,210]; cut [6,204] → keep [0,6] and [204,210]
    assert snippets._excise_span_from_segs([(0.0, 10.0), (200.0, 10.0)], 6.0, 204.0) == [
        (0.0, 6.0),
        (204.0, 6.0),
    ]


def test_excise_load_waits_collapses_long_wait_keeping_lead_in():
    # scene seg master [100,135]; a wait_for at abs 110 lasting 18s (ends 128).
    out = snippets.excise_load_waits(
        [(100.0, 35.0)],
        [{"scene_index": 1, "start_seconds": 110.0, "duration_seconds": 18.0}],
        lead_in=1.2,
        threshold=3.0,
    )
    # cut [111.2, 128] (keep the 1.2s lead-in) → [100,111.2] + [128,135]
    assert out == [(100.0, 11.2), (128.0, 7.0)]


def test_excise_load_waits_ignores_short_settle():
    # a 2s wait_for is a settle, not a load worth collapsing → untouched.
    segs = [(100.0, 35.0)]
    assert (
        snippets.excise_load_waits(
            segs, [{"scene_index": 1, "start_seconds": 110.0, "duration_seconds": 2.0}]
        )
        == segs
    )


def test_build_snippets_excises_recorded_load_wait():
    """A recorded wait_for span collapses a mid-scene load even in a teach scene
    with no clip (de-dwell a no-op) — the excise is ground-truth, not pixels."""
    spec = {"scenes": [{"title": "S", "pace": "teach", "narrative": "n"}]}
    report = {
        "scenes": [{"scene_index": 1, "start_seconds": 100.0, "duration_seconds": 35.0}],
        "load_waits": [
            {"scene_index": 1, "start_seconds": 110.0, "duration_seconds": 18.0, "target": "Done"}
        ],
    }
    snips = snippets.build_snippets(
        narrative_slug="x", spec=spec, report=report,
        source_clip_local=None, source_clip_hosted=None,
    )
    assert snips[0]["segments"] == [
        {"start_seconds": 100.0, "duration_seconds": 11.2},
        {"start_seconds": 128.0, "duration_seconds": 7.0},
    ]
    assert snips[0]["duration_seconds"] == pytest.approx(18.2)
