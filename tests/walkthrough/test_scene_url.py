"""Per-scene ``url`` field tests.

Pins the new ``Scene.url`` field (added in this PR) — declarative starting
URL beats inferring from the first ``goto`` action. The recorder's
``build_scenes_from_spec`` resolution order (url → first goto → None) is
covered separately by the integration path; here we just confirm the
schema accepts and validates the field.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ddd.schemas.models import Scene  # noqa: E402

_BASE = dict(
    persona="lead", title="Open the dashboard", show="Lead opens dashboard.",
    concept_claim="The dashboard exists.", provenance="dashboard-open",
)


def test_scene_url_defaults_to_none():
    """Existing specs that don't set ``url`` keep validating."""
    s = Scene.model_validate(_BASE)
    assert s.url is None


def test_scene_url_accepts_path_relative():
    s = Scene.model_validate({**_BASE, "url": "/microplans/program/133/"})
    assert s.url == "/microplans/program/133/"


def test_scene_url_accepts_absolute():
    s = Scene.model_validate({**_BASE, "url": "https://labs.connect.dimagi.com/microplans/glossary/"})
    assert s.url.startswith("https://")


def test_scene_url_round_trips_through_model_dump():
    s = Scene.model_validate({**_BASE, "url": "/x"})
    assert s.model_dump()["url"] == "/x"
