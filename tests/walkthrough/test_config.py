"""Unit tests for RecorderConfig presets + overrides."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.config import RecorderConfig  # noqa: E402


def test_default_is_medium():
    # Bare ``RecorderConfig()`` is the medium-pace preset — changing nothing
    # in a spec must produce the same video pace as before the refactor.
    c = RecorderConfig()
    assert c.initial_hold_ms == 1500
    assert c.typing_delay_ms == 45
    assert c.post_click_settle_ms == 900


def test_for_pace_fast_is_faster():
    fast = RecorderConfig.for_pace("fast")
    med = RecorderConfig.for_pace("medium")
    assert fast.typing_delay_ms < med.typing_delay_ms
    assert fast.post_click_settle_ms < med.post_click_settle_ms
    assert fast.scroll_speed_px_s > med.scroll_speed_px_s


def test_for_pace_slow_is_slower():
    slow = RecorderConfig.for_pace("slow")
    med = RecorderConfig.for_pace("medium")
    assert slow.typing_delay_ms > med.typing_delay_ms
    assert slow.post_click_settle_ms > med.post_click_settle_ms
    assert slow.scroll_speed_px_s < med.scroll_speed_px_s


def test_for_pace_unknown_falls_back_to_medium():
    assert RecorderConfig.for_pace("turbo") == RecorderConfig()
    assert RecorderConfig.for_pace(None) == RecorderConfig()


def test_with_overrides_replaces_subset():
    c = RecorderConfig.for_pace("medium").with_overrides({"typing_delay_ms": 20})
    assert c.typing_delay_ms == 20
    # Untouched fields stay at the preset.
    assert c.initial_hold_ms == 1500
    assert c.post_click_settle_ms == 900


def test_with_overrides_ignores_unknown_keys():
    # Forward compat: a spec targeting a newer recorder that knows about
    # ``mouse_acceleration`` shouldn't blow up an older recorder that doesn't.
    c = RecorderConfig().with_overrides({"mouse_acceleration": 0.9, "typing_delay_ms": 20})
    assert c.typing_delay_ms == 20
    assert not hasattr(c, "mouse_acceleration")


def test_with_overrides_empty_returns_self():
    c = RecorderConfig()
    assert c.with_overrides(None) is c
    assert c.with_overrides({}) is c


def test_config_is_frozen():
    c = RecorderConfig()
    import dataclasses
    try:
        c.typing_delay_ms = 99  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("RecorderConfig should be frozen")
