"""Tests for skipping ``initial_hold_ms`` + ``goto_settle_ms`` when the
first action of a scene is ``wait_for``.

Background: at the top of every scene the orchestrator does
``page.wait_for_timeout(initial_hold_ms)`` — a blind 800-2500ms hold to
let the page settle after navigation. ``goto_and_settle`` does another
blind ``page.wait_for_timeout(goto_settle_ms)`` (600-2000ms). When the
first scripted action is ``wait_for`` (e.g. "wait for 'Microplan
portfolio' to appear"), those two blind holds are pure dead air on top of
the wait_for — the wait_for IS the settle.

This test pins:
  - first action ``wait_for`` → neither ``initial_hold_ms`` nor
    ``goto_settle_ms`` fires
  - first action ``click`` / ``scroll_to`` / anything-else → both still fire
    (back-compat with existing specs that don't open with wait_for)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.config import RecorderConfig  # noqa: E402
from scripts.walkthrough._lib.orchestrator import Recorder  # noqa: E402


# Sentinel pace settings so we can identify which hold a timeout came from:
# initial_hold_ms=111, goto_settle_ms=222, final_hold_ms=333. The
# dispatcher's per-action timeouts won't collide with these (they're
# 0/45/300/etc).
SENTINEL_CONFIG = RecorderConfig(
    initial_hold_ms=111,
    final_hold_ms=333,
    min_hold_ms=0,
    goto_settle_ms=222,
)


class FakePage:
    """Page-shaped stub that records ``wait_for_timeout`` calls.

    The dispatcher path runs through ``execute_action`` for whatever the
    first action is — we use ``hold`` / ``press`` / ``wait_for`` because
    they're target-less so the dispatcher resolves them without needing
    real DOM. For ``wait_for``, the dispatcher calls
    ``page.wait_for_selector`` / ``page.wait_for_function`` which we stub
    to return immediately.
    """

    def __init__(self, *, url: str = "https://example.com/"):
        self.url = url
        self.timeouts: list[int] = []
        self.gotos: list[str] = []
        self.wait_for_selector_calls: list[str] = []
        self.wait_for_function_calls: list[str] = []

    def wait_for_timeout(self, ms):
        self.timeouts.append(int(ms))

    def wait_for_load_state(self, *args, **kwargs):
        pass

    def goto(self, url, *, wait_until=None, timeout=None):
        self.gotos.append(url)
        self.url = url

    def wait_for_selector(self, selector, *, timeout=None, state=None):
        self.wait_for_selector_calls.append(selector)

        class _Handle:
            def click(self_inner, *a, **k):
                pass

            def scroll_into_view_if_needed(self_inner, *a, **k):
                pass

        return _Handle()

    def wait_for_function(self, expr, *, timeout=None):
        self.wait_for_function_calls.append(expr)

    def evaluate(self, *a, **k):
        return None

    @property
    def keyboard(self):
        class _K:
            def press(self, *a, **k):
                pass

            def type(self, *a, **k):
                pass

        return _K()


def _scene(actions, *, url="https://example.com/x"):
    return {"title": "test", "url": url, "actions": actions, "scene_index": 1}


def test_initial_hold_fires_when_first_action_is_not_waitfor():
    """First action is ``scroll_to`` — initial_hold_ms (111) must appear."""
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    rec.run_scene(page, _scene([{"kind": "scroll_to", "target": "Anything"}]))
    assert 111 in page.timeouts, (
        f"initial_hold_ms (111) should fire when first action isn't wait_for; got {page.timeouts}"
    )


def test_initial_hold_skipped_when_first_action_is_waitfor():
    """First action is ``wait_for`` — initial_hold_ms (111) must NOT appear."""
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    rec.run_scene(page, _scene([{"kind": "wait_for", "target": "Loaded"}]))
    assert 111 not in page.timeouts, (
        f"initial_hold_ms (111) should be skipped when first action is wait_for; got {page.timeouts}"
    )


def test_goto_settle_fires_when_first_action_is_not_waitfor():
    """First action is ``press`` — goto_settle_ms (222) must appear."""
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    rec.run_scene(page, _scene([{"kind": "press"}]))
    assert 222 in page.timeouts, (
        f"goto_settle_ms (222) should fire when first action isn't wait_for; got {page.timeouts}"
    )


def test_goto_settle_skipped_when_first_action_is_waitfor():
    """First action is ``wait_for`` — goto_settle_ms (222) must NOT appear."""
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    rec.run_scene(page, _scene([{"kind": "wait_for", "target": "Loaded"}]))
    assert 222 not in page.timeouts, (
        f"goto_settle_ms (222) should be skipped when first action is wait_for; got {page.timeouts}"
    )


def test_empty_actions_keeps_initial_hold_and_goto_settle():
    """No actions at all — back-compat: both holds fire (the static-scene
    fallback path relies on the initial hold for a frame-able first
    moment)."""
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    rec.run_scene(page, _scene([]))
    assert 111 in page.timeouts, f"initial_hold_ms should fire on empty actions; got {page.timeouts}"
    assert 222 in page.timeouts, f"goto_settle_ms should fire on empty actions; got {page.timeouts}"


def test_final_hold_always_fires():
    """final_hold_ms is unrelated to the first-action optimization — it
    must always fire regardless of what the first action is."""
    page = FakePage()
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    rec.run_scene(page, _scene([{"kind": "wait_for", "target": "Loaded"}]))
    assert 333 in page.timeouts, f"final_hold_ms (333) must always fire; got {page.timeouts}"


def test_no_url_no_goto_settle_at_all():
    """When a scene has no url (continue-on-previous-page pattern), the
    orchestrator doesn't call ``goto_and_settle`` at all — neither
    goto_settle_ms NOR initial_hold_ms behavior is affected by the
    skip-on-waitfor logic for the goto path.

    Initial_hold_ms is still skipped on wait_for though — the optimization
    isn't gated on having navigated.
    """
    page = FakePage(url="https://example.com/already-here")
    rec = Recorder(config=SENTINEL_CONFIG, base_url="https://example.com")
    # No url → no goto, no goto_settle_ms
    scene = {"title": "continue", "actions": [{"kind": "wait_for", "target": "Loaded"}], "scene_index": 1}
    rec.run_scene(page, scene)
    assert 222 not in page.timeouts, f"no goto → no goto_settle_ms; got {page.timeouts}"
    assert 111 not in page.timeouts, f"wait_for first → no initial_hold_ms; got {page.timeouts}"
