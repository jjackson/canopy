"""Tests for ``scene.video_hold_seconds`` as the per-scene end-of-scene hold.

Background: ``video_hold_seconds`` was advertised in the walkthrough SKILL
("dwell this long instead of scroll-paced timing") and threaded through
``build_scenes_from_spec``, but NOTHING consumed it after the orchestrator
refactor — a silent no-op. The timing-model consolidation gives it one
defined meaning: it overrides ``final_hold_ms`` (the global end-of-scene
hold) for that scene only. Mid-scene dwells belong to ``hold`` actions.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.config import RecorderConfig  # noqa: E402
from scripts.walkthrough._lib.orchestrator import Recorder  # noqa: E402

# Sentinel pacing so each timeout is identifiable in the call log.
SENTINEL_CONFIG = RecorderConfig(
    initial_hold_ms=111,
    final_hold_ms=333,
    min_hold_ms=0,
    goto_settle_ms=222,
)


class FakePage:
    """Minimal page-shaped stub recording ``wait_for_timeout`` calls."""

    def __init__(self):
        self.url = "https://example.com/here"
        self.timeouts: list[int] = []

    def wait_for_timeout(self, ms):
        self.timeouts.append(int(ms))

    def wait_for_load_state(self, *a, **k):
        pass

    def goto(self, url, *, wait_until=None, timeout=None):
        self.url = url

    def evaluate(self, *a, **k):
        return None

    @property
    def keyboard(self):
        class _K:
            def press(self, *a, **k):
                pass

        return _K()


def test_video_hold_seconds_overrides_final_hold():
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    scene = {
        "title": "dwell",
        "actions": [{"kind": "press"}],
        "video_hold_seconds": 3,
        "scene_index": 1,
    }
    rec.run_scene(page, scene)
    assert 3000 in page.timeouts, f"override (3000) should fire; got {page.timeouts}"
    assert 333 not in page.timeouts, (
        f"final_hold_ms (333) must be REPLACED by the override, not added; got {page.timeouts}"
    )


def test_default_final_hold_when_no_override():
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    scene = {"title": "plain", "actions": [{"kind": "press"}], "scene_index": 1}
    rec.run_scene(page, scene)
    assert 333 in page.timeouts, f"final_hold_ms (333) should fire; got {page.timeouts}"


def test_fractional_video_hold_seconds():
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    scene = {
        "title": "half",
        "actions": [{"kind": "press"}],
        "video_hold_seconds": 1.5,
        "scene_index": 1,
    }
    rec.run_scene(page, scene)
    assert 1500 in page.timeouts, f"1.5s override → 1500ms; got {page.timeouts}"


def test_none_video_hold_seconds_falls_back():
    """build_scenes_from_spec passes ``None`` through for scenes without the
    key — that must mean 'no override', not a 0ms hold."""
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    scene = {
        "title": "explicit-none",
        "actions": [{"kind": "press"}],
        "video_hold_seconds": None,
        "scene_index": 1,
    }
    rec.run_scene(page, scene)
    assert 333 in page.timeouts, f"None → default final_hold_ms (333); got {page.timeouts}"
