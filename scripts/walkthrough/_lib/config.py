"""Timing configuration for the walkthrough recorder.

Before this module the recorder's pacing was a constellation of magic numbers
scattered across the primitives — a 250ms here, a 900ms there, a 45ms typing
delay in three different places. Spec authors who wanted a faster-typing demo
or a longer post-click settle had no knob to turn; you had to fork the lib.

Now a single :class:`RecorderConfig` dataclass owns every timing constant. Three
presets — ``fast``, ``medium`` (default), ``slow`` — cover the common video
pacing choices. A spec can override any subset of fields via
``video_recorder_config: { typing_delay_ms: 20 }`` in the YAML.

Two layers of knobs:

- **Scene-level** (``initial_hold_ms``, ``final_hold_ms``, ``min_hold_ms``,
  ``scroll_speed_px_s``) — consumed by the orchestrator between actions.
- **Action-level** (``typing_delay_ms``, ``pre_click_dwell_ms``,
  ``post_click_settle_ms``, …) — consumed by individual primitives.

A primitive that wants to tune its own pacing reads from ``self.config`` (or
the ``config=`` kwarg). A primitive that takes ``config=None`` defaults to
:class:`RecorderConfig` (medium pace) so existing call sites keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace


@dataclass(frozen=True)
class RecorderConfig:
    """Every timing knob for the recorder.

    Defaults match the medium-pace recorder behavior before the refactor —
    so changing nothing in a spec gets you the same video pace.
    """

    # ---- scene-level (consumed by orchestrator) --------------------------
    initial_hold_ms: int = 1500
    """Hold after navigating into a scene, before actions run."""

    final_hold_ms: int = 1000
    """Hold after a scene's actions finish, before moving to the next scene."""

    min_hold_ms: int = 4000
    """Floor on a scene's elapsed time — short scenes get padded."""

    scroll_speed_px_s: int = 600
    """Eased-scroll speed for the static-scene fallback (no actions)."""

    # ---- action-level: cursor motion -------------------------------------
    cursor_steps: int = 36
    """Mouse-move steps for a normal glide — enough to animate the cursor overlay."""

    cursor_steps_short: int = 10
    """Mouse-move steps for a final re-centring before a click."""

    pre_click_dwell_ms: int = 250
    """Pause after the cursor lands on a click target, before mouse-down."""

    # ---- action-level: per-primitive settle ------------------------------
    glide_dwell_ms: int = 350
    """Default ``_glide_to`` dwell — the pause the cursor takes once it arrives."""

    click_dwell_ms: int = 500
    """Pre-click ``_glide_to`` dwell — slightly longer so the viewer registers it."""

    post_click_settle_ms: int = 900
    """Hold after a regular text/CSS click, for the UI to react."""

    menu_click_settle_ms: int = 700
    """Hold after a dropdown/popover menu item click (usually quicker than a button)."""

    pre_fill_dwell_ms: int = 200
    """Pause after the cursor lands on a fill target, before focusing the field."""

    post_fill_settle_ms: int = 300
    """Hold after a fill, for live updates (typeahead, debounced search) to render."""

    pre_select_dwell_ms: int = 200
    """Pause after the cursor lands on a ``<select>``, before flipping the option."""

    post_select_settle_ms: int = 300
    """Hold after picking an option, for the page to react to the change."""

    scroll_settle_ms: int = 600
    """Hold after a ``scroll_to`` or page-level scroll."""

    goto_settle_ms: int = 1200
    """Hold after a ``goto`` (navigation + brief idle)."""

    crossfade: bool = True
    """Crossfade the outgoing scene's frame over the incoming page to hide the
    browser's white navigation flash. Set False to disable (e.g. when debugging
    raw page state, or for specs where the flash is wanted)."""

    # ---- action-level: native <select> reveal ----------------------------
    select_reveal: bool = True
    """Render a synthetic dropdown over a native ``<select>`` before committing
    the choice, so the recording actually SHOWS the options and which one is
    picked. Native OS select popups can't be screen-recorded; without this the
    closed widget just silently flips value."""

    select_reveal_dwell_ms: int = 1000
    """How long the synthetic dropdown stays open (cursor gliding to the chosen
    option) before the value commits and it closes — long enough for a viewer
    to read the options and see which one is picked."""

    # ---- action-level: typing --------------------------------------------
    typing_delay_ms: int = 45
    """Per-keystroke delay during ``fill`` / ``type`` so the typing is visible."""

    # ---- timeouts --------------------------------------------------------
    glide_timeout_ms: int = 6000
    """Max time ``_glide_to`` waits for the target to exist before giving up."""

    interaction_timeout_ms: int = 6000
    """Max time ``click_text`` / ``fill_field`` / ``select_option`` wait for the target."""

    menu_timeout_ms: int = 5000
    """Max time ``click_menu_item`` waits for the menu item to render."""

    wait_for_timeout_ms: int = 12000
    """Max time ``wait_for`` waits for text/selector to appear."""

    goto_timeout_ms: int = 60000
    """Max time ``page.goto`` waits."""

    load_settle_timeout_ms: int = 8000
    """Max time the orchestrator waits for the ``load`` event after ``domcontentloaded``."""

    # ---- presets ---------------------------------------------------------
    @classmethod
    def for_pace(cls, pace: str | None) -> RecorderConfig:
        """Return a preset config for ``pace`` in {``fast``, ``medium``, ``slow``}.

        Unknown / ``None`` → ``medium`` (the default dataclass values). The
        preset adjusts both scene-level pacing and action-level pacing so a
        ``"fast"`` video also types faster and settles shorter, not just hops
        between scenes faster.
        """
        if pace == "fast":
            return cls(
                initial_hold_ms=800, final_hold_ms=500, min_hold_ms=2500,
                scroll_speed_px_s=1200,
                pre_click_dwell_ms=150, click_dwell_ms=300, glide_dwell_ms=200,
                post_click_settle_ms=400, menu_click_settle_ms=350,
                pre_fill_dwell_ms=100, post_fill_settle_ms=150,
                pre_select_dwell_ms=100, post_select_settle_ms=150,
                scroll_settle_ms=300, goto_settle_ms=600,
                typing_delay_ms=20,
            )
        if pace == "slow":
            return cls(
                initial_hold_ms=2500, final_hold_ms=1500, min_hold_ms=6000,
                scroll_speed_px_s=300,
                pre_click_dwell_ms=400, click_dwell_ms=800, glide_dwell_ms=550,
                post_click_settle_ms=1400, menu_click_settle_ms=1000,
                pre_fill_dwell_ms=350, post_fill_settle_ms=600,
                pre_select_dwell_ms=350, post_select_settle_ms=600,
                scroll_settle_ms=1000, goto_settle_ms=2000,
                typing_delay_ms=80,
            )
        return cls()

    def with_overrides(self, overrides: dict | None) -> RecorderConfig:
        """Return a copy with fields in ``overrides`` replaced.

        Used to apply a spec's ``video_recorder_config`` block on top of the
        pace preset. Unknown keys are ignored (forward-compat for specs that
        target a newer recorder).
        """
        if not overrides:
            return self
        valid = {f.name for f in fields(self)}
        clean = {k: v for k, v in overrides.items() if k in valid}
        return replace(self, **clean) if clean else self
