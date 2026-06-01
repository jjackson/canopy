"""Unit tests for the dispatcher's verb table + error tagging.

Uses a fake Page that records calls instead of driving a real browser, so the
dispatcher logic (kind routing, error_kind tagging, ActionResult fields,
must_succeed → raise) can be exercised without Playwright/Chromium.

The actual cursor-glide / DOM-resolve paths are exercised against a real
browser via the manual walkthrough flow — not unit-tested here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib.recorder import execute_action  # noqa: E402
from scripts.walkthrough._lib.results import ActionAssertError  # noqa: E402


class FakeKeyboard:
    def __init__(self):
        self.typed: list[tuple[str, int]] = []
        self.pressed: list[str] = []

    def type(self, text, *, delay=0):
        self.typed.append((text, delay))

    def press(self, key):
        self.pressed.append(key)


class FakePage:
    """A Playwright Page-shaped object that records calls. Just enough surface
    for the dispatcher's no-target verbs (``type``, ``press``, ``hold``, ``goto``)
    plus a stub for ``wait_for_timeout`` / ``goto``. The target-requiring verbs
    (``click``, ``fill``, ``select``, etc.) call into primitives that need a
    real browser — those are tested via the manual walkthrough loop."""

    def __init__(self, *, url=""):
        self.url = url
        self.keyboard = FakeKeyboard()
        self.timeouts: list[int] = []
        self.gotos: list[tuple[str, dict]] = []

    def wait_for_timeout(self, ms):
        self.timeouts.append(int(ms))

    def goto(self, url, *, wait_until=None, timeout=None):
        self.gotos.append((url, {"wait_until": wait_until, "timeout": timeout}))
        self.url = url


def test_type_records_kind_and_value():
    page = FakePage()
    r = execute_action(page, {"kind": "type", "value": "hello"})
    assert r.ok is True
    assert r.kind == "type"
    assert r.value == "hello"
    assert page.keyboard.typed == [("hello", 45)]


def test_press_default_enter():
    page = FakePage()
    r = execute_action(page, {"kind": "press"})
    assert r.ok is True
    assert page.keyboard.pressed == ["Enter"]


def test_press_explicit_key():
    page = FakePage()
    execute_action(page, {"kind": "press", "value": "Escape"})
    assert page.keyboard.pressed == ["Escape"]


def test_hold_uses_seconds():
    page = FakePage()
    execute_action(page, {"kind": "hold", "seconds": 1.5})
    assert page.timeouts == [1500]


def test_hold_falls_back_to_value():
    page = FakePage()
    execute_action(page, {"kind": "hold", "value": "0.4"})
    assert page.timeouts == [400]


def test_goto_absolute_url():
    page = FakePage()
    execute_action(page, {"kind": "goto", "target": "https://example.com/x"})
    assert page.gotos[0][0] == "https://example.com/x"


def test_goto_relative_url_prepends_base():
    page = FakePage()
    execute_action(page, {"kind": "goto", "target": "/dashboard"},
                   base_url="https://example.com")
    assert page.gotos[0][0] == "https://example.com/dashboard"


def test_unknown_kind_returns_error_kind():
    page = FakePage()
    r = execute_action(page, {"kind": "teleport"})
    assert r.ok is False
    assert r.error_kind == "unknown_kind"


def test_unknown_kind_with_must_succeed_raises():
    page = FakePage()
    with pytest.raises(ActionAssertError):
        execute_action(page, {"kind": "teleport", "must_succeed": True})


def test_action_result_carries_note():
    page = FakePage()
    r = execute_action(page, {"kind": "type", "value": "x", "note": "the typing scene"})
    assert r.note == "the typing scene"


def test_result_elapsed_ms_is_int():
    page = FakePage()
    r = execute_action(page, {"kind": "press"})
    assert isinstance(r.elapsed_ms, int)
    assert r.elapsed_ms >= 0
