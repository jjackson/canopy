"""Unit tests for late-binding ``${var}`` resolution + order-aware validation.

The capture/late-binding contract has three pure-Python pieces, all in
``scripts/narrative/substitution.py``:

  - ``resolve_string`` — partial resolution: substitute the vars present in the
    live map, leave unknown (capture-bound) ones verbatim.
  - ``scene_capture_vars`` — the vars a scene's ``capture`` actions BIND.
  - ``ordered_placeholder_violations`` — a ${var} is valid iff a setup output
    OR an EARLIER capture provides it (var-before-capture errors; var-after
    passes).

Plus an orchestrator-level test that a var captured in an earlier scene flows
into a LATER scene's url + action target (the whole point).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.narrative.substitution import (  # noqa: E402
    has_unresolved,
    ordered_placeholder_violations,
    resolve_string,
    scene_capture_vars,
    substitute_scenes,
)
from scripts.walkthrough._lib.orchestrator import Recorder  # noqa: E402
from scripts.walkthrough._lib import orchestrator as orch_mod  # noqa: E402


# ---------------------------------------------------------------------------
# resolve_string — partial / late
# ---------------------------------------------------------------------------


def test_resolve_string_substitutes_known_leaves_unknown():
    out = resolve_string("/sol/${sol_id}/resp/${resp_id}/", {"sol_id": "207"})
    assert out == "/sol/207/resp/${resp_id}/"


def test_resolve_string_coerces_numbers():
    assert resolve_string("/x/${n}/", {"n": 42}) == "/x/42/"


def test_resolve_string_passes_through_non_strings():
    assert resolve_string(None, {"a": "1"}) is None


def test_has_unresolved():
    assert has_unresolved("/x/${id}/") is True
    assert has_unresolved("/x/207/") is False


# ---------------------------------------------------------------------------
# scene_capture_vars
# ---------------------------------------------------------------------------


def test_scene_capture_vars_in_order():
    scene = {
        "actions": [
            {"kind": "click", "target": "Create"},
            {"kind": "capture", "var": "sol_id", "source": "url", "pattern": r"(\d+)"},
            {"kind": "capture", "var": "resp_id", "source": "url", "pattern": r"(\d+)"},
        ]
    }
    assert scene_capture_vars(scene) == ["sol_id", "resp_id"]


def test_scene_capture_vars_empty_for_no_capture():
    assert scene_capture_vars({"actions": [{"kind": "click", "target": "X"}]}) == []


# ---------------------------------------------------------------------------
# ordered_placeholder_violations
# ---------------------------------------------------------------------------


def _capture(var):
    return {"kind": "capture", "var": var, "source": "url", "pattern": r"(\d+)"}


def test_var_after_capture_passes():
    scenes = [
        {"title": "create", "url": "/sol/new/", "actions": [{"kind": "click", "target": "Create"}, _capture("sol_id")]},
        {"title": "view", "url": "/sol/${sol_id}/", "actions": []},
    ]
    assert ordered_placeholder_violations(scenes, setup_vars=set()) == []


def test_var_before_capture_errors():
    # The same var is captured — but in a LATER scene than where it's used.
    scenes = [
        {"title": "view", "url": "/sol/${sol_id}/", "actions": []},
        {"title": "create", "url": "/sol/new/", "actions": [_capture("sol_id")]},
    ]
    violations = ordered_placeholder_violations(scenes, setup_vars=set())
    assert len(violations) == 1
    assert "sol_id" in violations[0]


def test_setup_var_is_available_from_the_start():
    scenes = [{"title": "view", "url": "/run/${run_id}/", "actions": []}]
    assert ordered_placeholder_violations(scenes, setup_vars={"run_id"}) == []


def test_within_scene_capture_then_use_in_later_action_passes():
    scenes = [
        {
            "title": "create+open",
            "url": "/sol/new/",
            "actions": [
                {"kind": "click", "target": "Create"},
                _capture("sol_id"),
                {"kind": "click", "target": "View ${sol_id}"},
            ],
        }
    ]
    assert ordered_placeholder_violations(scenes, setup_vars=set()) == []


def test_scene_url_cannot_use_its_own_capture():
    # A scene's URL resolves at scene START, before its own actions run — so a
    # var the scene itself captures is NOT available to its own url.
    scenes = [
        {"title": "self", "url": "/sol/${sol_id}/", "actions": [_capture("sol_id")]},
    ]
    violations = ordered_placeholder_violations(scenes, setup_vars=set())
    assert len(violations) == 1
    assert "url references ${sol_id}" in violations[0]


# ---------------------------------------------------------------------------
# substitute_scenes — partial (allow_unresolved)
# ---------------------------------------------------------------------------


def test_substitute_scenes_leaves_capture_bound_intact():
    scenes = [
        {"title": "s", "url": "/run/${run_id}/sol/${sol_id}/", "actions": []},
    ]
    out = substitute_scenes(scenes, {"run_id": "3699"}, allow_unresolved={"sol_id"})
    assert out[0]["url"] == "/run/3699/sol/${sol_id}/"


def test_substitute_scenes_still_errors_on_truly_missing():
    import pytest

    scenes = [{"title": "s", "url": "/x/${missing}/", "actions": []}]
    with pytest.raises(Exception):
        substitute_scenes(scenes, {}, allow_unresolved={"other"})


# ---------------------------------------------------------------------------
# orchestrator — a captured var flows into a LATER scene url + action target
# ---------------------------------------------------------------------------


class _FakePage:
    def __init__(self, url=""):
        self.url = url

    def wait_for_timeout(self, ms):
        pass

    def screenshot(self, *a, **k):
        raise RuntimeError("no screenshot in test")

    def evaluate(self, *a, **k):
        return 0

    def goto(self, url, **k):
        self.url = url


def test_captured_var_flows_into_later_scene(monkeypatch):
    """Scene 1 captures sol_id off the page; scene 2's url + a later action
    target resolve to the captured value."""
    page = _FakePage(url="https://app/")
    recorder = Recorder(base_url="https://app")

    seen_targets: list[str] = []
    seen_gotos: list[str] = []

    # Drive goto through the recorder's goto_and_settle, which calls page.goto.
    def fake_execute_action(pg, action, *, base_url="", config=None, variables=None):
        from scripts.walkthrough._lib.results import ActionResult

        kind = action.get("kind")
        if kind == "capture":
            # Simulate reading the id off the page the "Create" click landed on.
            variables[action["var"]] = "207"
            return ActionResult(kind="capture", ok=True, capture_var=action["var"], capture_value="207")
        if kind == "click":
            seen_targets.append(action.get("target"))
        return ActionResult(kind=kind, ok=True, target=action.get("target"))

    monkeypatch.setattr(orch_mod, "execute_action", fake_execute_action)

    # Capture page.goto via goto_for_scene → goto_and_settle. Stub the settle.
    orig_goto = page.goto

    def tracking_goto(url, **k):
        seen_gotos.append(url)
        orig_goto(url, **k)

    page.goto = tracking_goto
    # Neutralize crossfade screenshot (page.screenshot raises) — _capture_frame
    # swallows exceptions, so this is fine; just disable crossfade for clarity.
    recorder.config = recorder.config.with_overrides({"crossfade": False})

    scenes = [
        {
            "title": "create",
            "url": "/sol/new/",
            "actions": [{"kind": "click", "target": "Create"}, {"kind": "capture", "var": "sol_id"}],
            "scene_index": 1,
        },
        {
            "title": "view",
            "url": "/sol/${sol_id}/",
            "actions": [{"kind": "click", "target": "Edit ${sol_id}"}],
            "scene_index": 2,
        },
    ]
    recorder.run(page, scenes)

    # Scene 2's url resolved to the captured value.
    assert "https://app/sol/207/" in seen_gotos
    # The later action target resolved too.
    assert "Edit 207" in seen_targets
    assert recorder.variables["sol_id"] == "207"
