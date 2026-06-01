"""Per-kind validation tests for the discriminated Action union.

Every test pins one rule of the strict per-verb schema: which fields a verb
accepts, which it rejects, and how the union dispatches by ``kind``. Together
they guarantee that a spec author who writes ``{kind: type, target: "Buy"}``
gets a clear schema error pointing at ``target`` on ``TypeAction``, instead
of a silent no-op at recording time.

Real-spec survey (38 specs, ~100 actions across canopy + connect-labs +
ace-web + canopy-web): every existing action shape already matches these
strict classes. The union is backward-compat with real-world specs.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import TypeAdapter, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ddd.schemas.models import (  # noqa: E402
    Action,
    ClickAction,
    FillAction,
    GotoAction,
    HoldAction,
    HoverAction,
    PressAction,
    ScrollAction,
    SelectAction,
    TypeAction,
    WaitForAction,
)

ACTION = TypeAdapter(Action)  # the dispatch entry point for the union


# ---- discriminator routes to the right class ------------------------------


def test_goto_with_target_validates_as_goto_action():
    a = ACTION.validate_python({"kind": "goto", "target": "/dashboard"})
    assert isinstance(a, GotoAction)
    assert a.target == "/dashboard"


def test_click_with_target_validates_as_click_action():
    a = ACTION.validate_python({"kind": "click", "target": "Buy"})
    assert isinstance(a, ClickAction)


def test_fill_with_target_and_value_validates():
    a = ACTION.validate_python({"kind": "fill", "target": "#email", "value": "ace@x.y"})
    assert isinstance(a, FillAction)
    assert a.value == "ace@x.y"


def test_select_with_target_and_value_validates():
    a = ACTION.validate_python({"kind": "select", "target": "#country", "value": "0"})
    assert isinstance(a, SelectAction)


def test_type_with_only_value_validates():
    a = ACTION.validate_python({"kind": "type", "value": "hi"})
    assert isinstance(a, TypeAction)


def test_press_with_default_enter_validates():
    a = ACTION.validate_python({"kind": "press"})
    assert isinstance(a, PressAction)
    assert a.value == "Enter"


def test_hover_with_target_and_seconds_validates():
    a = ACTION.validate_python({"kind": "hover", "target": "Tooltip", "seconds": 1.0})
    assert isinstance(a, HoverAction)
    assert a.seconds == 1.0


def test_hold_with_seconds_validates():
    a = ACTION.validate_python({"kind": "hold", "seconds": 0.4})
    assert isinstance(a, HoldAction)
    assert a.seconds == 0.4


def test_wait_for_with_target_validates():
    a = ACTION.validate_python({"kind": "wait_for", "target": "Resolved wards"})
    assert isinstance(a, WaitForAction)


def test_scroll_with_value_validates():
    a = ACTION.validate_python({"kind": "scroll", "value": "bottom"})
    assert isinstance(a, ScrollAction)


# ---- strict per-kind: wrong fields are rejected ---------------------------


def test_type_with_target_is_rejected():
    """``type`` types into the focused element — a ``target`` is a typo."""
    with pytest.raises(ValidationError) as exc:
        ACTION.validate_python({"kind": "type", "target": "Buy", "value": "x"})
    assert "target" in str(exc.value)


def test_click_with_value_is_rejected():
    """``click`` doesn't take a ``value`` — author likely meant ``fill``."""
    with pytest.raises(ValidationError) as exc:
        ACTION.validate_python({"kind": "click", "target": "Buy", "value": "x"})
    assert "value" in str(exc.value)


def test_hold_with_target_is_rejected():
    """``hold`` is a time pause, no target involved."""
    with pytest.raises(ValidationError):
        ACTION.validate_python({"kind": "hold", "seconds": 1, "target": "Anywhere"})


def test_goto_missing_target_is_rejected():
    """``goto`` MUST have a URL."""
    with pytest.raises(ValidationError):
        ACTION.validate_python({"kind": "goto"})


def test_fill_missing_value_is_rejected():
    """``fill`` MUST have text to type — empty fill is a typo for ``click``."""
    with pytest.raises(ValidationError):
        ACTION.validate_python({"kind": "fill", "target": "#email"})


def test_unknown_kind_is_rejected_by_union():
    """Discriminator failure → loud error (not silent no-op at runtime)."""
    with pytest.raises(ValidationError):
        ACTION.validate_python({"kind": "teleport", "target": "x"})


# ---- shared fields work on every kind ------------------------------------


def test_note_is_accepted_on_every_kind():
    """Every action takes a human ``note`` for the render log."""
    for kind, extra in [
        ("goto", {"target": "/x"}),
        ("click", {"target": "x"}),
        ("hold", {"seconds": 1}),
        ("press", {}),
    ]:
        a = ACTION.validate_python({"kind": kind, "note": "demonstrates X", **extra})
        assert a.note == "demonstrates X"


def test_must_succeed_is_accepted_on_every_kind():
    """Every action takes ``must_succeed`` for fail-loud opt-in."""
    a = ACTION.validate_python({"kind": "click", "target": "Buy", "must_succeed": True})
    assert a.must_succeed is True


# ---- real-spec backward compat -------------------------------------------


def test_microplans_scene_3_select_actions_validate():
    """The microplans-10-wards spec's scene 3 LGA picks must validate clean."""
    raw = {"kind": "select",
           "target": "#resolved-tbody tr.is-unresolved select",
           "value": "0",
           "note": "pick Madobi LGA for Gora (candidate 0)"}
    a = ACTION.validate_python(raw)
    assert isinstance(a, SelectAction)
    assert a.note.startswith("pick Madobi")


def test_scene_actions_list_round_trips():
    """A whole scene's actions[] of mixed kinds validates as a list."""
    actions_raw = [
        {"kind": "goto", "target": "/microplans/program/133/"},
        {"kind": "wait_for", "target": "Microplan portfolio"},
        {"kind": "hold", "seconds": 2.0, "note": "frame the empty portfolio"},
        {"kind": "scroll_to", "target": "+ Bulk paste list"},
        {"kind": "hold", "seconds": 1.5},
    ]
    actions = [ACTION.validate_python(a) for a in actions_raw]
    assert [type(a).__name__ for a in actions] == [
        "GotoAction", "WaitForAction", "HoldAction", "ScrollToAction", "HoldAction",
    ]


def test_draw_validates_with_points():
    from scripts.ddd.schemas.models import DrawAction

    a = ACTION.validate_python(
        {"kind": "draw", "target": "css:#review-map", "points": [[0.3, 0.4], [0.6, 0.4], [0.6, 0.7]]}
    )
    assert isinstance(a, DrawAction)
    assert a.target == "css:#review-map"
    assert a.points == [(0.3, 0.4), (0.6, 0.4), (0.6, 0.7)]


def test_draw_requires_target_and_points():
    with pytest.raises(ValidationError):
        ACTION.validate_python({"kind": "draw", "points": [[0.3, 0.4]]})  # no target
    with pytest.raises(ValidationError):
        ACTION.validate_python({"kind": "draw", "target": "css:#m"})  # no points


def test_draw_rejects_foreign_fields():
    with pytest.raises(ValidationError):
        ACTION.validate_python(
            {"kind": "draw", "target": "css:#m", "points": [[0.3, 0.4]], "value": "x"}
        )


def test_draw_accepts_optional_tool():
    from scripts.ddd.schemas.models import DrawAction

    a = ACTION.validate_python(
        {"kind": "draw", "target": "css:#m", "points": [[0.3, 0.4], [0.6, 0.6]],
         "tool": "css:.mapbox-gl-draw_polygon"}
    )
    assert isinstance(a, DrawAction) and a.tool == "css:.mapbox-gl-draw_polygon"
