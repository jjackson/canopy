"""Unit tests for per-scene video timestamps in the recorder.

The DDD product-findings review deep-links the iteration clip at the moment a
finding's scene starts (``<clip_url>#t=<seconds>``).  That requires the
recorder to know WHERE each scene sits on the recording timeline.  These
tests pin:

  - ``Recorder.run_scene`` records one timing entry per scene with a
    cumulative ``start_seconds`` offset and a positive ``duration_seconds``
  - the offset is measured from ``recording_epoch`` (set by the CLI at page
    creation, so pre-scene auth nav counts toward scene 1's start) and
    defaults lazily to the first scene when unset
  - scenes dropped by ``--skip-empty-scenes`` get NO entry (they never run)
  - entries survive ``RunReport.as_dict()`` / ``to_json()``
  - ``scene_timestamps()`` reads ``scene_index -> start_seconds`` back from a
    report dict, tolerating old reports with no ``scenes`` key
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.config import RecorderConfig  # noqa: E402
from scripts.walkthrough._lib.orchestrator import Recorder  # noqa: E402
from scripts.walkthrough._lib.results import RunReport, scene_timestamps  # noqa: E402
from scripts.walkthrough.record_video import filter_empty_scenes  # noqa: E402


class _FakeKeyboard:
    def press(self, *a, **k):
        pass

    def type(self, *a, **k):
        pass


class FakePage:
    """Just enough Page surface for the orchestrator loop (no real waits)."""

    def __init__(self):
        self.url = "https://example.com/"
        self.keyboard = _FakeKeyboard()

    def wait_for_timeout(self, ms):
        pass

    def wait_for_load_state(self, *args, **kwargs):
        pass

    def goto(self, url, *, wait_until=None, timeout=None):
        self.url = url

    def screenshot(self, **kwargs):
        raise RuntimeError("no screenshots in fake page")

    def evaluate(self, *a, **k):
        pass


def _fast_config() -> RecorderConfig:
    """Zero out every hold so tests run instantly."""
    return RecorderConfig(
        initial_hold_ms=0,
        final_hold_ms=0,
        min_hold_ms=0,
        goto_settle_ms=0,
        goto_timeout_ms=1000,
        load_settle_timeout_ms=1,
    )


def _scenes(n: int) -> list[dict]:
    return [
        {
            "url": f"https://example.com/page{i}",
            "title": f"Scene {i}",
            "actions": [{"kind": "hold", "seconds": 0}],
            "scene_index": i,
        }
        for i in range(1, n + 1)
    ]


# ---- accumulation ----------------------------------------------------------


def test_run_records_one_timing_entry_per_scene():
    rec = Recorder(config=_fast_config())
    rec.run(FakePage(), _scenes(3))

    assert [e["scene_index"] for e in rec.report.scenes] == [1, 2, 3]
    assert [e["title"] for e in rec.report.scenes] == ["Scene 1", "Scene 2", "Scene 3"]


def test_start_seconds_are_cumulative_and_nonnegative():
    rec = Recorder(config=_fast_config())
    rec.run(FakePage(), _scenes(3))

    starts = [e["start_seconds"] for e in rec.report.scenes]
    assert starts == sorted(starts)
    assert starts[0] >= 0.0
    # Each scene starts at (roughly) the previous scene's start + duration.
    for prev, cur in zip(rec.report.scenes, rec.report.scenes[1:]):
        assert cur["start_seconds"] >= prev["start_seconds"]
        assert cur["start_seconds"] >= prev["start_seconds"] + prev["duration_seconds"] - 0.05

    assert all(e["duration_seconds"] >= 0.0 for e in rec.report.scenes)


def test_epoch_defaults_to_first_scene_start_when_unset():
    rec = Recorder(config=_fast_config())
    assert rec.recording_epoch is None
    rec.run(FakePage(), _scenes(1))
    assert rec.recording_epoch is not None
    # First scene's offset is ~0 when the epoch defaulted lazily.
    assert rec.report.scenes[0]["start_seconds"] < 0.5


def test_explicit_epoch_shifts_offsets():
    """A CLI-stamped epoch earlier than scene 1 (auth nav time) shifts starts."""
    import time

    rec = Recorder(config=_fast_config())
    rec.recording_epoch = time.monotonic() - 10.0  # pretend 10s of pre-roll
    rec.run(FakePage(), _scenes(1))
    assert rec.report.scenes[0]["start_seconds"] >= 10.0


def test_original_spec_index_preserved_for_partial_runs():
    rec = Recorder(config=_fast_config())
    scenes = _scenes(5)
    rec.run(FakePage(), [scenes[2]])  # only spec scene 3
    assert [e["scene_index"] for e in rec.report.scenes] == [3]


# ---- skip-empty-scenes interaction ----------------------------------------


def test_skipped_empty_scenes_get_no_timestamps():
    scenes = _scenes(4)
    scenes[1]["actions"] = []  # spec scene 2 is narrative-only
    scenes[3]["actions"] = []  # spec scene 4 is narrative-only

    surviving = filter_empty_scenes(scenes)
    rec = Recorder(config=_fast_config())
    rec.run(FakePage(), surviving)

    assert [e["scene_index"] for e in rec.report.scenes] == [1, 3]
    ts = scene_timestamps(rec.report.as_dict())
    assert set(ts) == {1, 3}


# ---- serialization + reader helper -----------------------------------------


def test_timing_entries_survive_report_json_roundtrip():
    rec = Recorder(config=_fast_config())
    rec.run(FakePage(), _scenes(2))

    parsed = json.loads(rec.report.to_json())
    assert "scenes" in parsed
    ts = scene_timestamps(parsed)
    assert set(ts) == {1, 2}
    assert ts[1] <= ts[2]


def test_scene_timestamps_tolerates_old_reports():
    # Reports written before per-scene timing existed have no "scenes" key.
    assert scene_timestamps({"total": 3, "ok": 3, "failed": 0, "actions": []}) == {}
    assert scene_timestamps({}) == {}
    # Malformed entries are skipped, not fatal.
    assert scene_timestamps(
        {"scenes": [{"scene_index": "2", "start_seconds": "4.5"}, {"bogus": True}, "junk"]}
    ) == {2: 4.5}


def test_empty_report_has_empty_scenes_list():
    assert RunReport().as_dict()["scenes"] == []
