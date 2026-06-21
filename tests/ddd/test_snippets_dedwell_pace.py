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
