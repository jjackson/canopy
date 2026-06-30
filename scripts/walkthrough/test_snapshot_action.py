"""Tests for the `snapshot` action — mid-scene canonical-frame capture.

Run: uv run python -m pytest scripts/walkthrough/test_snapshot_action.py -q
"""

from pathlib import Path
from unittest.mock import MagicMock

from scripts.walkthrough._lib.orchestrator import Recorder


def _rec(tmp_path: Path) -> Recorder:
    return Recorder(snapshot_dir=tmp_path)


def test_take_snapshot_skips_explicitly_snapshotted_scene(tmp_path: Path):
    r = _rec(tmp_path)
    # pretend a `snapshot` action already wrote scene 3's canonical frame
    r._explicit_snapshot_scenes.add(3)
    # _screenshot_with_settle_retry must NOT be called for a flagged scene
    r._screenshot_with_settle_retry = MagicMock(return_value=True)
    page = MagicMock()

    r.take_snapshot(page, {"actions": [{"kind": "snapshot"}]}, 3)

    r._screenshot_with_settle_retry.assert_not_called()
    assert 3 not in r.snapshots_taken
    assert not list(tmp_path.glob("scene_3.*"))  # nothing written


def test_take_snapshot_runs_for_unflagged_scene(tmp_path: Path):
    r = _rec(tmp_path)
    r._screenshot_with_settle_retry = MagicMock(return_value=True)
    page = MagicMock()
    page.evaluate.return_value = "body text"
    page.url = "https://labs/x"

    r.take_snapshot(page, {"actions": [{"kind": "click", "target": "x"}]}, 5)

    r._screenshot_with_settle_retry.assert_called_once()
    assert 5 in r.snapshots_taken
    assert (tmp_path / "scene_5_page_text.json").exists()  # text dump always written


def test_take_explicit_snapshot_writes_then_flags(tmp_path: Path):
    r = _rec(tmp_path)
    r._screenshot_with_settle_retry = MagicMock(return_value=True)
    page = MagicMock()
    page.evaluate.return_value = "coach feedback text"
    page.url = "https://labs/respond"

    # the snapshot action writes the canonical frame mid-scene...
    r.take_explicit_snapshot(page, {"actions": [{"kind": "snapshot"}]}, 6)
    assert 6 in r.snapshots_taken
    assert 6 in r._explicit_snapshot_scenes
    assert (tmp_path / "scene_6_page_text.json").exists()

    # ...and a SUBSEQUENT end-of-scene take_snapshot is a no-op (doesn't overwrite)
    r._screenshot_with_settle_retry.reset_mock()
    r.take_snapshot(page, {"actions": [{"kind": "snapshot"}]}, 6)
    r._screenshot_with_settle_retry.assert_not_called()
