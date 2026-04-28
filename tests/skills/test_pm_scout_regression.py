"""Regression test for the human-gated /canopy:pm-scout flow.

Per the autonomous-mode spec, the existing human-gated path MUST keep
working unchanged. These tests pin down the structural elements the flow
depends on so the autonomous-mode work cannot silently weaken them.
"""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL = PLUGIN_ROOT / "skills" / "product-management" / "SKILL.md"
PM_SCOUT = PLUGIN_ROOT / "commands" / "pm-scout.md"


def test_pm_scout_command_exists() -> None:
    assert PM_SCOUT.exists()


def test_pm_scout_invokes_product_management_skill() -> None:
    content = PM_SCOUT.read_text()
    assert "product-management" in content


def test_pm_scout_arguments_lens() -> None:
    content = PM_SCOUT.read_text()
    assert "argument-hint" in content or "lens" in content.lower()


def test_skill_keeps_phase_3_askuserquestion() -> None:
    content = SKILL.read_text()
    # Phase 3 in the human-gated flow is the AskUserQuestion menu.
    assert "AskUserQuestion" in content
    assert "Phase 3" in content


def test_skill_keeps_disposition_options() -> None:
    content = SKILL.read_text()
    for option in ("Do it", "Backlog", "Close", "Redirect"):
        assert option in content, f"disposition option missing from SKILL.md: {option}"


def test_skill_keeps_six_human_phases() -> None:
    content = SKILL.read_text()
    for phase in (
        "Phase 0",
        "Phase 1",
        "Phase 2",
        "Phase 3",
        "Phase 4",
        "Phase 5",
        "Phase 6",
    ):
        assert phase in content, f"human-gated {phase} missing"


def test_skill_keeps_lens_rotation() -> None:
    # Lenses are defined in the pm-scout command (the entry point for human-gated mode).
    content = PM_SCOUT.read_text()
    for lens in (
        "user-value",
        "adoption-blockers",
        "integration-depth",
        "trust-reliability",
        "tech-debt",
    ):
        assert lens in content, f"lens missing: {lens}"
