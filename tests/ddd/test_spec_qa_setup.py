"""spec_qa structural checks for the data-setup contract (rule i).

``${...}`` placeholders in scene URLs / action targets are resolved at render
time from ``setup.outputs`` — so a spec that uses them MUST declare where they
come from, or the recorder films a literal ``/runs/${run_id}/`` URL. The
converse is fine: a setup block whose outputs declare variables the scenes
never use is not an error (the generator may emit more than one demo needs).
"""
from __future__ import annotations

from scripts.ddd.spec_qa import spec_qa


def _spec_data(
    url: str | None = None,
    actions: list[dict] | None = None,
    setup: dict | None = None,
) -> dict:
    """Build a minimal valid UnifiedSpec dict with optional placeholders/setup."""
    scene: dict = {
        "persona": "alice",
        "title": "Submit Form",
        "show": "navigate to /form, fill fields, click Submit",
        "concept_claim": "Users can submit a form and see confirmation within 2 seconds",
        "provenance": "S1",
        "features": [
            {
                "id": "F1",
                "description": "Submit button on the form page triggers a POST request",
                "verify": "pytest: POST /form returns 200 and response contains confirmation_id",
            }
        ],
    }
    if url is not None:
        scene["url"] = url
    if actions is not None:
        scene["actions"] = actions
    data: dict = {
        "name": "My Feature Walkthrough",
        "narrative": "Demonstrates the core user journey",
        "base_url": "http://localhost:8000",
        "personas": {
            "alice": {
                "name": "Alice",
                "role": "Program Manager",
                "color": "#3B82F6",
                "intro": "Alice manages program delivery.",
            }
        },
        "scenes": [scene],
    }
    if setup is not None:
        data["setup"] = setup
    return data


_SETUP = {
    "command": "python scripts/walkthroughs/demo/regenerate.py",
    "outputs": "scripts/walkthroughs/demo/outputs.json",
}


def test_placeholder_in_url_without_setup_fails():
    result = spec_qa(_spec_data(url="/workflow/runs/${run_id}/"))
    assert result.verdict == "fail"
    assert "${...}" in result.blocking_reason
    assert "run_id" in result.blocking_reason
    assert "setup" in result.blocking_reason


def test_placeholder_in_action_target_without_setup_fails():
    result = spec_qa(
        _spec_data(actions=[{"kind": "click", "target": "Run ${run_id} details"}])
    )
    assert result.verdict == "fail"
    assert "run_id" in result.blocking_reason


def test_placeholder_with_setup_but_no_outputs_fails():
    result = spec_qa(
        _spec_data(
            url="/workflow/runs/${run_id}/",
            setup={"command": "python scripts/walkthroughs/demo/regenerate.py"},
        )
    )
    assert result.verdict == "fail"
    assert "setup.outputs" in result.blocking_reason


def test_placeholder_with_setup_outputs_passes():
    result = spec_qa(_spec_data(url="/workflow/runs/${run_id}/", setup=_SETUP))
    assert result.verdict == "pass"


def test_setup_without_placeholders_is_fine():
    """Declared-but-unused outputs are not an error."""
    result = spec_qa(_spec_data(url="/dashboard/", setup=_SETUP))
    assert result.verdict == "pass"


def test_static_spec_without_setup_still_passes():
    result = spec_qa(_spec_data(url="/dashboard/"))
    assert result.verdict == "pass"
