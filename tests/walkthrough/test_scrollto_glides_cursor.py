"""Tests for ``scroll_to``'s pre-scroll cursor glide + post-scroll re-glide.

Background: ``click_text`` and ``fill_field`` both glide the synthetic cursor
onto their target BEFORE acting — the viewer sees the cursor arrive on the
button, then the button is clicked. ``scroll_to`` used to skip this step:
it called ``scroll_into_view_if_needed`` + a smooth-scroll JS evaluate,
parked the cursor wherever it had been, and waited ``scroll_settle_ms``.

When the scroll was a no-op (target already in view — common because spec
authors ``scroll_to`` defensively before a click), the screen was completely
frozen for ``scroll_settle_ms``. The fix: resolve target → glide cursor onto
target → smooth-scroll → re-measure → short glide so the cursor follows the
element to its new viewport position. Identical shape to ``click_text``'s
re-measure-before-click step.

These tests pin BOTH glides via a fake Playwright Page that records
``mouse.move`` + ``evaluate`` calls in order. The actual scroll motion is
exercised against a real browser via the manual walkthrough flow.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.config import RecorderConfig  # noqa: E402
from scripts.walkthrough._lib.recorder import scroll_to  # noqa: E402


class FakeMouse:
    """Records every ``move(x, y, steps=...)`` call in order."""

    def __init__(self):
        self.moves: list[tuple[float, float, int]] = []

    def move(self, x, y, *, steps=1):
        self.moves.append((float(x), float(y), int(steps)))


class FakeLocator:
    """Locator stub with a mutable bounding box (so we can simulate the
    smooth-scroll moving the element under the cursor).

    ``boxes`` is the queue ``bounding_box()`` consumes in order — first call
    returns the pre-scroll position, second returns the post-scroll one.
    The recorder calls ``bounding_box()`` indirectly via ``measure_box``
    after the smooth-scroll, so the second box must reflect the new viewport
    position of the element.
    """

    def __init__(self, *, boxes):
        # Each box is a Playwright-shaped dict: {x, y, width, height}.
        self.boxes = list(boxes)
        self._idx = 0
        self.scroll_into_view_calls = 0

    def bounding_box(self):
        # ``measure_box`` calls ``bounding_box()`` once per measurement.
        # We pop from the queue but never go past the last entry — that
        # keeps repeat calls (post-scroll re-measure) returning the last
        # known position rather than raising.
        i = min(self._idx, len(self.boxes) - 1)
        self._idx += 1
        return self.boxes[i]

    def scroll_into_view_if_needed(self, *, timeout=None):
        self.scroll_into_view_calls += 1


class FakePage:
    """Page-shaped stub. Only the surface ``scroll_to`` touches:
    ``mouse.move``, ``evaluate``, ``wait_for_timeout``."""

    def __init__(self):
        self.mouse = FakeMouse()
        self.evaluates: list[tuple[str, object]] = []
        self.timeouts: list[int] = []

    def evaluate(self, expr, arg=None):
        self.evaluates.append((expr, arg))
        return None

    def wait_for_timeout(self, ms):
        self.timeouts.append(int(ms))


# Centre of the pre-scroll box: x=100+200/2=200, y=400+50/2=425
PRE_BOX = {"x": 100.0, "y": 400.0, "width": 200.0, "height": 50.0}
PRE_CENTRE = (200.0, 425.0)

# After the smooth-scroll, the element's box has moved up (e.g. by 300px) —
# centre is now (200, 125). This is the post-scroll re-measure case.
POST_BOX = {"x": 100.0, "y": 100.0, "width": 200.0, "height": 50.0}
POST_CENTRE = (200.0, 125.0)


def _patch_resolve(monkeypatch, locator):
    """Stub ``resolve_target`` so we don't need a real DOM.

    ``scroll_to`` is the function under test; it imports ``resolve_target``
    at module level. We patch the binding inside the recorder module.
    """
    from scripts.walkthrough._lib import recorder as recorder_mod
    from scripts.walkthrough._lib.targets import ResolvedTarget

    rt = ResolvedTarget(locator=locator, box={"x": PRE_CENTRE[0], "y": PRE_CENTRE[1]}, kind="text")
    monkeypatch.setattr(recorder_mod, "resolve_target", lambda *a, **k: rt)


def test_scrollto_glides_cursor_onto_target_before_scroll(monkeypatch):
    """The first thing ``scroll_to`` does (after resolving) is glide the
    cursor onto the target — same shape as ``click_text``'s pre-click glide.

    A no-op-scroll scene (target already in view) would otherwise freeze
    the screen for ``scroll_settle_ms``; the glide guarantees the viewer
    sees motion."""
    page = FakePage()
    loc = FakeLocator(boxes=[PRE_BOX])
    _patch_resolve(monkeypatch, loc)

    cfg = RecorderConfig()
    ok = scroll_to(page, "Some button", config=cfg)

    assert ok is True
    assert page.mouse.moves, "scroll_to must glide the cursor — got no mouse.move calls"
    # First move = pre-scroll glide to the target's current centre.
    first_x, first_y, first_steps = page.mouse.moves[0]
    assert (first_x, first_y) == PRE_CENTRE, (
        f"first glide should land on pre-scroll target centre {PRE_CENTRE}; got ({first_x}, {first_y})"
    )
    assert first_steps == cfg.cursor_steps, (
        f"first glide should use full cursor_steps ({cfg.cursor_steps}); got {first_steps}"
    )


def test_scrollto_glides_before_smooth_scroll_evaluate(monkeypatch):
    """Order matters: the cursor must glide onto the target BEFORE the
    smooth-scroll JS runs. If we scrolled first, the element would move
    out from under the cursor's intended landing position."""
    page = FakePage()
    loc = FakeLocator(boxes=[PRE_BOX])
    _patch_resolve(monkeypatch, loc)

    # Stamp the action order via a shared timeline. ``FakeMouse.move`` and
    # ``FakePage.evaluate`` both append to it — we just need to know which
    # came first.
    timeline: list[str] = []

    original_move = page.mouse.move
    def tracked_move(x, y, *, steps=1):
        timeline.append("move")
        return original_move(x, y, steps=steps)
    page.mouse.move = tracked_move  # type: ignore[method-assign]

    original_eval = page.evaluate
    def tracked_eval(expr, arg=None):
        timeline.append("evaluate")
        return original_eval(expr, arg)
    page.evaluate = tracked_eval  # type: ignore[method-assign]

    scroll_to(page, "Target", config=RecorderConfig())

    assert timeline.index("move") < timeline.index("evaluate"), (
        f"cursor must glide BEFORE smooth-scroll evaluate; timeline={timeline}"
    )


def test_scrollto_remeasures_and_reglides_after_scroll(monkeypatch):
    """After the smooth-scroll, the locator's box has moved (the element
    is now at a different viewport y). The cursor must follow it via a
    re-measure + short glide — same re-measure pattern ``click_text`` uses
    before clicking a settled element.

    The first glide uses the resolver's cached ``rt.box`` (the centre of
    PRE_BOX). The post-scroll re-glide measures the locator fresh via
    ``measure_box(rt.locator)`` which calls ``bounding_box()`` — we hand
    it POST_BOX so the cursor ends on POST_CENTRE.
    """
    page = FakePage()
    # Only POST_BOX in the queue — the pre-scroll glide reads the resolver's
    # cached centre, not bounding_box().
    loc = FakeLocator(boxes=[POST_BOX])
    _patch_resolve(monkeypatch, loc)

    cfg = RecorderConfig()
    scroll_to(page, "Target", config=cfg)

    assert len(page.mouse.moves) >= 2, (
        f"scroll_to should glide twice (pre + post); got {len(page.mouse.moves)} moves"
    )
    last_x, last_y, last_steps = page.mouse.moves[-1]
    assert (last_x, last_y) == POST_CENTRE, (
        f"final cursor position should be post-scroll centre {POST_CENTRE}; got ({last_x}, {last_y})"
    )
    assert last_steps == cfg.cursor_steps_short, (
        f"re-glide should use cursor_steps_short ({cfg.cursor_steps_short}); got {last_steps}"
    )


def test_scrollto_skips_reglide_when_locator_has_no_box(monkeypatch):
    """If ``measure_box`` returns None after the scroll (element detached,
    bounding_box() returned falsy), the recorder must NOT crash and must
    NOT issue a follow-up glide to nowhere. Only the pre-scroll glide
    fires; ``scroll_settle_ms`` still runs."""
    page = FakePage()

    class DetachedLocator:
        def bounding_box(self):
            # Only called once by ``measure_box`` after the scroll. The
            # pre-scroll glide uses the resolver's cached ``rt.box``
            # directly, so the first bounding_box() call IS the
            # post-scroll re-measure — which returns None to simulate the
            # element having detached mid-scroll.
            return None

        def scroll_into_view_if_needed(self, *, timeout=None):
            pass

    loc = DetachedLocator()
    _patch_resolve(monkeypatch, loc)

    cfg = RecorderConfig()
    ok = scroll_to(page, "Target", config=cfg)

    assert ok is True, "scroll_to should still succeed if post-scroll re-measure returns None"
    # Pre-scroll glide always fires; post-scroll glide is conditional on a
    # measurable box. So exactly one move call when the element detaches.
    assert len(page.mouse.moves) == 1, (
        f"detached post-scroll locator should yield exactly one glide; got {len(page.mouse.moves)}"
    )
    assert cfg.scroll_settle_ms in page.timeouts, (
        f"scroll_settle_ms ({cfg.scroll_settle_ms}) must still fire; got {page.timeouts}"
    )


def test_scrollto_returns_false_when_target_unresolved(monkeypatch):
    """Unchanged contract: a missing target returns False with no glide,
    no scroll, no settle. Back-compat for callers that branch on the
    return value."""
    page = FakePage()
    from scripts.walkthrough._lib import recorder as recorder_mod
    monkeypatch.setattr(recorder_mod, "resolve_target", lambda *a, **k: None)

    ok = scroll_to(page, "Nonexistent", config=RecorderConfig())

    assert ok is False
    assert page.mouse.moves == [], "no glide when target unresolved"
    assert page.evaluates == [], "no smooth-scroll when target unresolved"
    assert page.timeouts == [], "no settle when target unresolved"
