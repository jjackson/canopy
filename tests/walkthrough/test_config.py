"""Unit tests for RecorderConfig presets + overrides."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.config import (  # noqa: E402
    FLOW_CURSOR_SPEEDUP,
    FLOW_CURSOR_STEPS_MIN,
    FLOW_GOTO_SETTLE_MS,
    FLOW_HOLD_CEILING_MS,
    HOLD_ACTION_FLOW_CEILING_MS,
    RecorderConfig,
    apply_scene_pace,
)


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


# --------------------------------------------------------------------------- #
# Scene pace (teach | flow) — apply_scene_pace
# --------------------------------------------------------------------------- #


def test_pace_teach_is_identity():
    # The default tempo: a teach scene records under the unchanged config, so
    # every existing (pace-less) spec is byte-for-byte the same.
    c = RecorderConfig.for_pace("medium")
    assert apply_scene_pace(c, "teach") is c
    assert apply_scene_pace(c, None) is c
    assert apply_scene_pace(c, "unknown-value") is c


def test_pace_flow_clamps_holds_to_ceiling():
    # Medium preset holds are all well above the flow ceiling, so flow clamps
    # them down to it. (Resolved flow hold ≤ ceiling; teach hold unchanged.)
    teach = RecorderConfig.for_pace("medium")
    flow = apply_scene_pace(teach, "flow")
    assert teach.initial_hold_ms == 1500  # teach unchanged
    assert flow.initial_hold_ms <= FLOW_HOLD_CEILING_MS
    assert flow.final_hold_ms <= FLOW_HOLD_CEILING_MS
    assert flow.min_hold_ms <= FLOW_HOLD_CEILING_MS
    assert flow.post_click_settle_ms <= FLOW_HOLD_CEILING_MS
    assert flow.scroll_settle_ms <= FLOW_HOLD_CEILING_MS
    # The medium 1500ms initial hold is clamped exactly to the ceiling.
    assert flow.initial_hold_ms == FLOW_HOLD_CEILING_MS


def test_pace_flow_drops_goto_settle():
    flow = apply_scene_pace(RecorderConfig.for_pace("medium"), "flow")
    assert flow.goto_settle_ms <= FLOW_GOTO_SETTLE_MS


def test_pace_flow_only_clamps_down_never_pads():
    # A hold already SHORTER than the ceiling (the fast preset's 500ms final
    # hold, 400ms post-click settle) must be left as-is — flow compresses, it
    # never lengthens.
    fast = RecorderConfig.for_pace("fast")
    flow = apply_scene_pace(fast, "flow")
    assert flow.final_hold_ms == fast.final_hold_ms == 500
    assert flow.post_click_settle_ms == fast.post_click_settle_ms == 400


def test_pace_flow_speeds_cursor():
    teach = RecorderConfig.for_pace("medium")
    flow = apply_scene_pace(teach, "flow")
    # Fewer steps == faster glide (the overlay animates per step).
    assert flow.cursor_steps < teach.cursor_steps
    assert flow.cursor_steps == max(
        FLOW_CURSOR_STEPS_MIN, int(teach.cursor_steps / FLOW_CURSOR_SPEEDUP)
    )
    assert flow.cursor_steps_short >= FLOW_CURSOR_STEPS_MIN


def test_pace_flow_sets_hold_action_ceiling():
    teach = RecorderConfig.for_pace("medium")
    flow = apply_scene_pace(teach, "flow")
    # teach: no cap on explicit `hold` actions; flow: capped.
    assert teach.hold_action_ceiling_ms is None
    assert flow.hold_action_ceiling_ms == HOLD_ACTION_FLOW_CEILING_MS


def test_pace_flow_returns_a_distinct_frozen_config():
    teach = RecorderConfig.for_pace("medium")
    flow = apply_scene_pace(teach, "flow")
    assert flow is not teach
    assert isinstance(flow, RecorderConfig)
    # The base config is untouched (replace() returns a copy).
    assert teach.initial_hold_ms == 1500
