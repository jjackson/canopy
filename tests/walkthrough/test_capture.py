"""Unit tests for the ``capture`` action — late-binding ``${var}`` minting.

``capture`` is the on-camera half of the late-binding contract: a demo creates
an entity DURING recording, ``capture`` reads its id off the resulting page,
and LATER scenes resolve ``${that_id}`` to the real, freshly-minted value. No
fixed IDs, no per-render state resets.

These tests exercise the dispatcher + ``capture_value`` primitive against fakes
(no Playwright/Chromium):

  - capture from URL (regex group 1)
  - capture from element attribute and from element text
  - optional vs required pattern semantics
  - must_succeed failure (default True for capture)
  - the captured var lands in the live ``variables`` map (and override warns)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.walkthrough._lib import recorder as recorder_mod  # noqa: E402
from scripts.walkthrough._lib.recorder import (  # noqa: E402
    _apply_capture_pattern,
    capture_value,
    execute_action,
)
from scripts.walkthrough._lib.results import ActionAssertError  # noqa: E402


class FakePage:
    def __init__(self, *, url=""):
        self.url = url

    def wait_for_timeout(self, ms):  # capture never calls this, but be safe
        pass


class FakeLocator:
    """Minimal Locator-shaped stub for ``source: element`` capture."""

    def __init__(self, *, attrs=None, text=""):
        self._attrs = attrs or {}
        self._text = text

    def get_attribute(self, name, *, timeout=None):
        return self._attrs.get(name)

    def inner_text(self, *, timeout=None):
        return self._text


class FakeResolved:
    def __init__(self, locator):
        self.locator = locator
        self.box = {"x": 1, "y": 1}
        self.kind = "css"


# ---------------------------------------------------------------------------
# _apply_capture_pattern — the trim + regex-group core
# ---------------------------------------------------------------------------


def test_pattern_none_returns_whole_trimmed_value():
    assert _apply_capture_pattern("  207 ", None) == (True, "207")


def test_pattern_none_empty_fails():
    assert _apply_capture_pattern("   ", None) == (False, None)


def test_pattern_extracts_group_one():
    ok, val = _apply_capture_pattern("/solicitations/207/", r"/solicitations/(\d+)/")
    assert (ok, val) == (True, "207")


def test_pattern_no_group_fails():
    ok, val = _apply_capture_pattern("/solicitations/207/", r"/solicitations/\d+/")
    assert ok is False and val is None


def test_pattern_no_match_fails():
    ok, val = _apply_capture_pattern("/audits/9/", r"/solicitations/(\d+)/")
    assert ok is False and val is None


def test_pattern_invalid_regex_fails():
    ok, val = _apply_capture_pattern("anything", r"(unclosed")
    assert ok is False and val is None


# ---------------------------------------------------------------------------
# capture_value — source: url
# ---------------------------------------------------------------------------


def test_capture_from_url_regex_group():
    page = FakePage(url="https://x/solicitations/207/")
    ok, val = capture_value(page, {"source": "url", "pattern": r"/solicitations/(\d+)/"})
    assert (ok, val) == (True, "207")


def test_capture_from_url_requires_pattern():
    page = FakePage(url="https://x/solicitations/207/")
    ok, val = capture_value(page, {"source": "url"})
    assert ok is False and val is None


# ---------------------------------------------------------------------------
# capture_value — source: element
# ---------------------------------------------------------------------------


def test_capture_from_element_attr(monkeypatch):
    loc = FakeLocator(attrs={"href": "/response/42/edit"})
    monkeypatch.setattr(recorder_mod, "resolve_target", lambda *a, **k: FakeResolved(loc))
    page = FakePage()
    ok, val = capture_value(
        page,
        {"source": "element", "target": "css:a.view", "attr": "href", "pattern": r"response/(\d+)/"},
    )
    assert (ok, val) == (True, "42")


def test_capture_from_element_text_no_pattern(monkeypatch):
    loc = FakeLocator(text="  Response #88  ")
    monkeypatch.setattr(recorder_mod, "resolve_target", lambda *a, **k: FakeResolved(loc))
    page = FakePage()
    ok, val = capture_value(page, {"source": "element", "target": "css:.badge"})
    assert (ok, val) == (True, "Response #88")


def test_capture_from_element_text_with_pattern(monkeypatch):
    loc = FakeLocator(text="Response #88")
    monkeypatch.setattr(recorder_mod, "resolve_target", lambda *a, **k: FakeResolved(loc))
    page = FakePage()
    ok, val = capture_value(page, {"source": "element", "target": "css:.badge", "pattern": r"#(\d+)"})
    assert (ok, val) == (True, "88")


def test_capture_element_missing_target_fails():
    page = FakePage()
    ok, val = capture_value(page, {"source": "element", "attr": "href"})
    assert ok is False and val is None


def test_capture_element_unresolved_target_fails(monkeypatch):
    monkeypatch.setattr(recorder_mod, "resolve_target", lambda *a, **k: None)
    page = FakePage()
    ok, val = capture_value(page, {"source": "element", "target": "css:.nope"})
    assert ok is False and val is None


def test_capture_element_missing_attr_fails(monkeypatch):
    loc = FakeLocator(attrs={})  # no href
    monkeypatch.setattr(recorder_mod, "resolve_target", lambda *a, **k: FakeResolved(loc))
    page = FakePage()
    ok, val = capture_value(page, {"source": "element", "target": "css:a", "attr": "href"})
    assert ok is False and val is None


# ---------------------------------------------------------------------------
# execute_action — capture writes the live variables map
# ---------------------------------------------------------------------------


def test_execute_capture_writes_variable():
    page = FakePage(url="https://x/solicitations/207/")
    variables: dict = {}
    r = execute_action(
        page,
        {"kind": "capture", "var": "sol_id", "source": "url", "pattern": r"/solicitations/(\d+)/"},
        variables=variables,
    )
    assert r.ok is True
    assert r.kind == "capture"
    assert r.capture_var == "sol_id"
    assert r.capture_value == "207"
    assert variables["sol_id"] == "207"


def test_execute_capture_records_failure_in_result():
    page = FakePage(url="https://x/audits/9/")
    variables: dict = {}
    # must_succeed defaults True for capture, so a no-match must RAISE. Override
    # to False to inspect the failing result without the raise.
    r = execute_action(
        page,
        {
            "kind": "capture",
            "var": "sol_id",
            "source": "url",
            "pattern": r"/solicitations/(\d+)/",
            "must_succeed": False,
        },
        variables=variables,
    )
    assert r.ok is False
    assert r.error_kind == "capture_failed"
    assert "sol_id" not in variables


def test_execute_capture_must_succeed_defaults_true_and_raises():
    page = FakePage(url="https://x/audits/9/")
    with pytest.raises(ActionAssertError):
        execute_action(
            page,
            {"kind": "capture", "var": "sol_id", "source": "url", "pattern": r"/solicitations/(\d+)/"},
            variables={},
        )


def test_execute_capture_missing_var_fails():
    page = FakePage(url="https://x/solicitations/207/")
    r = execute_action(
        page,
        {"kind": "capture", "source": "url", "pattern": r"(\d+)", "must_succeed": False},
        variables={},
    )
    assert r.ok is False
    assert r.error_message and "var" in r.error_message


def test_execute_capture_override_wins(capsys):
    page = FakePage(url="https://x/solicitations/207/")
    variables = {"sol_id": "1"}  # pre-existing (e.g. a stale setup output)
    execute_action(
        page,
        {"kind": "capture", "var": "sol_id", "source": "url", "pattern": r"/solicitations/(\d+)/"},
        variables=variables,
    )
    assert variables["sol_id"] == "207"  # captured wins
    out = capsys.readouterr().out
    assert "overrides" in out
