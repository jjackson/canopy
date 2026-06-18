"""Unit tests for ``${var}`` placeholder substitution (the data-setup contract).

Pins ``scripts/narrative/substitution.py`` — the single source of truth for
placeholder syntax shared by the recorder (``record_video.py``) and the
structural QA gate (``spec_qa.py``):

  - Happy path: ``${var}`` in ``Scene.url`` and action ``target`` / ``value``
    resolves from the variables map; numbers coerce via str; the input scene
    dicts are NOT mutated (the spec file on disk is never rewritten).
  - Missing var: a HARD error (``UnresolvedPlaceholderError``) raised before
    any recording starts, listing the missing var AND the available keys.
  - Substitution scope is narrow: only url/target/value — prose fields that
    happen to contain ``${...}`` are not scanned.

The motivation lives in verified-monitoring: its spec hardcoded run_id=3720
while the regenerate script minted a fresh run each reseed — the spec silently
went stale every time. ``${run_id}`` + a setup block closes that gap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.narrative.substitution import (  # noqa: E402
    UnresolvedPlaceholderError,
    find_placeholders,
    scenes_placeholders,
    substitute_scenes,
)


def _scene(**overrides) -> dict:
    base = {
        "title": "Maya opens the run",
        "url": "/workflow/runs/${run_id}/",
        "actions": [
            {"kind": "click", "target": "Run ${run_id} details"},
            {"kind": "fill", "target": "Audit note", "value": "auto-${audit_id}"},
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# find_placeholders / scenes_placeholders
# ---------------------------------------------------------------------------


def test_find_placeholders_extracts_identifier_names():
    assert find_placeholders("/runs/${run_id}/x/${audit_id}") == {"run_id", "audit_id"}


def test_find_placeholders_ignores_non_strings_and_non_identifiers():
    assert find_placeholders(None) == set()
    assert find_placeholders(42) == set()
    # non-identifier body (shell arithmetic in a code sample) is not a placeholder
    assert find_placeholders("echo ${1:-default} ${a-b}") == set()


def test_scenes_placeholders_scans_url_target_value_only():
    scene = _scene(show="prose mentions ${not_a_var} but show is not scanned")
    assert scenes_placeholders([scene]) == {"run_id", "audit_id"}


def test_scenes_placeholders_empty_for_static_spec():
    assert scenes_placeholders([{"title": "t", "url": "/dashboard/", "actions": []}]) == set()


# ---------------------------------------------------------------------------
# substitute_scenes — happy path
# ---------------------------------------------------------------------------


def test_substitute_resolves_url_target_and_value():
    out = substitute_scenes([_scene()], {"run_id": 3721, "audit_id": "A-9"})
    assert out[0]["url"] == "/workflow/runs/3721/"
    assert out[0]["actions"][0]["target"] == "Run 3721 details"
    assert out[0]["actions"][1]["value"] == "auto-A-9"


def test_substitute_does_not_mutate_input():
    scenes = [_scene()]
    substitute_scenes(scenes, {"run_id": 1, "audit_id": 2})
    assert scenes[0]["url"] == "/workflow/runs/${run_id}/"
    assert scenes[0]["actions"][0]["target"] == "Run ${run_id} details"


def test_substitute_noop_for_static_scenes():
    scenes = [{"title": "t", "url": "/dashboard/", "actions": [{"kind": "click", "target": "Go"}]}]
    out = substitute_scenes(scenes, {})
    assert out[0]["url"] == "/dashboard/"
    assert out[0]["actions"][0]["target"] == "Go"


# ---------------------------------------------------------------------------
# substitute_scenes — hard errors
# ---------------------------------------------------------------------------


def test_missing_var_is_hard_error_listing_missing_and_available():
    with pytest.raises(UnresolvedPlaceholderError) as exc:
        substitute_scenes([_scene()], {"run_id": 3721, "other": "x"})
    msg = str(exc.value)
    assert "audit_id" in msg          # the missing var, by name
    assert "run_id" in msg            # the available keys are listed
    assert "other" in msg


def test_no_variables_at_all_lists_none_available():
    with pytest.raises(UnresolvedPlaceholderError) as exc:
        substitute_scenes([_scene()], {})
    assert "(none)" in str(exc.value)
