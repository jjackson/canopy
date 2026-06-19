"""Unit tests for multi-frame (before/after) scene capture.

A DDD scene is judged from ONE still screenshot — the end-frame. For an
EFFECTING scene (one that clicks/fills/submits) the judge can't see what
CHANGED: the before state is gone by the time the frame is taken. With
``capture_action_frames=True`` the recorder also writes ``scene_<N>_before.png``
at the action loop's starting line, so the judge can compare before→after.

These pin the contract:
  - default OFF → single-frame behavior unchanged (no _before.png)
  - ON + effecting action → a _before.png is written before the action loop
  - ON + non-effecting-only scene (hover/scroll) → no _before.png
  - the before-frame is tracked separately from snapshots_taken (the canonical
    end-frame list stays unchanged)
  - filenames use the 1-based ORIGINAL spec index
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.orchestrator import (  # noqa: E402
    Recorder,
    _scene_has_effecting_action,
)


class FakePage:
    """Page-shaped stub that records screenshot calls (mirrors the snapshot test)."""

    def __init__(self, *, url: str = "https://example.com/"):
        self.url = url
        self.screenshots: list[dict] = []
        self.body_text = "settled steady-state"

    def wait_for_timeout(self, ms):
        pass

    def wait_for_load_state(self, *args, **kwargs):
        pass

    def goto(self, url, *, wait_until=None, timeout=None):
        self.url = url

    def screenshot(self, *, path: str, full_page: bool = False, timeout: int | None = None):
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n")
        self.screenshots.append({"path": path, "full_page": full_page})

    def evaluate(self, script, *args):
        if "innerText" in script:
            return self.body_text
        if "scrollY" in script:
            return 0
        return None


# ---- _scene_has_effecting_action -------------------------------------------


def test_effecting_detection():
    assert _scene_has_effecting_action({"actions": [{"kind": "click", "target": "X"}]})
    assert _scene_has_effecting_action({"actions": [{"kind": "fill", "target": "X", "value": "y"}]})
    assert _scene_has_effecting_action(
        {"actions": [{"kind": "hover", "target": "X"}, {"kind": "select", "target": "S", "value": "1"}]}
    )
    assert not _scene_has_effecting_action({"actions": [{"kind": "hover", "target": "X"}]})
    assert not _scene_has_effecting_action({"actions": [{"kind": "scroll_to", "target": "X"}]})
    assert not _scene_has_effecting_action({"actions": []})
    assert not _scene_has_effecting_action({})


# ---- default OFF: single-frame unchanged -----------------------------------


def test_default_off_writes_no_before_frame(tmp_path):
    page = FakePage(url="https://example.com/form")
    rec = Recorder(snapshot_dir=tmp_path)  # capture_action_frames defaults False
    scene = {"title": "Submit", "actions": [{"kind": "press", "value": "Enter"}], "scene_index": 3}
    rec.run_scene(page, scene)

    assert (tmp_path / "scene_3.png").exists()
    assert not (tmp_path / "scene_3_before.png").exists()
    assert rec.before_frames_taken == []
    assert rec.snapshots_taken == [3]


# ---- ON: before + after for an effecting scene -----------------------------


def test_on_writes_before_and_after_for_effecting_scene(tmp_path):
    page = FakePage(url="https://example.com/form")
    rec = Recorder(snapshot_dir=tmp_path, capture_action_frames=True)
    scene = {
        "title": "Dana creates the solicitation",
        "actions": [
            {"kind": "fill", "target": "Title", "value": "Q3"},
            {"kind": "click", "target": "Create"},
        ],
        "scene_index": 2,
    }
    rec.run_scene(page, scene)

    before = tmp_path / "scene_2_before.png"
    after = tmp_path / "scene_2.png"
    assert before.exists(), "before-frame should be written for an effecting scene"
    assert after.exists(), "canonical after-frame should still be written"
    # before-frame tracked separately; snapshots_taken stays the canonical list
    assert rec.before_frames_taken == [2]
    assert rec.snapshots_taken == [2]
    # both PNGs captured
    paths = [s["path"] for s in page.screenshots]
    assert str(before) in paths
    assert str(after) in paths


def test_before_frame_precedes_after_frame(tmp_path):
    """The before-frame screenshot must be taken BEFORE the after-frame."""
    page = FakePage(url="https://example.com/form")
    rec = Recorder(snapshot_dir=tmp_path, capture_action_frames=True)
    scene = {"title": "X", "actions": [{"kind": "click", "target": "Go"}], "scene_index": 1}
    rec.run_scene(page, scene)

    paths = [s["path"] for s in page.screenshots]
    assert paths.index(str(tmp_path / "scene_1_before.png")) < paths.index(
        str(tmp_path / "scene_1.png")
    )


# ---- ON: non-effecting scene gets NO before-frame --------------------------


def test_on_skips_before_frame_for_hover_only_scene(tmp_path):
    page = FakePage(url="https://example.com/map")
    rec = Recorder(snapshot_dir=tmp_path, capture_action_frames=True)
    scene = {
        "title": "Inspect the map",
        "actions": [{"kind": "hover", "target": "Ward"}, {"kind": "scroll_to", "target": "Legend"}],
        "scene_index": 4,
    }
    rec.run_scene(page, scene)

    assert (tmp_path / "scene_4.png").exists()
    assert not (tmp_path / "scene_4_before.png").exists()
    assert rec.before_frames_taken == []


def test_on_preserves_original_spec_index(tmp_path):
    page = FakePage(url="https://example.com/form")
    rec = Recorder(snapshot_dir=tmp_path, capture_action_frames=True)
    scene = {"title": "X", "actions": [{"kind": "click", "target": "Go"}], "scene_index": 7}
    rec.run_scene(page, scene)
    assert (tmp_path / "scene_7_before.png").exists()
    assert rec.before_frames_taken == [7]


def test_no_snapshot_dir_no_before_frame(tmp_path):
    page = FakePage()
    rec = Recorder(capture_action_frames=True)  # no snapshot_dir
    scene = {"title": "X", "actions": [{"kind": "click", "target": "Go"}], "scene_index": 1}
    rec.run_scene(page, scene)
    assert rec.before_frames_taken == []
