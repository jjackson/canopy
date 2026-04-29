"""Structural invariants for the autonomous PM mode.

These tests don't exercise behavior — they pin down that the artifacts
(templates, commands, scripts) exist and contain the load-bearing strings
the cycle relies on. Drift here is a bug.
"""
from __future__ import annotations

import re
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL_DIR = PLUGIN_ROOT / "skills" / "product-management"
TEMPLATES = SKILL_DIR / "templates" / "autonomous"
SCRIPTS = SKILL_DIR / "scripts"
COMMANDS = PLUGIN_ROOT / "commands"


def test_templates_exist() -> None:
    expected = {"cycle.md", "config-schema.md", "convince-self-gate.md", "email-format.md"}
    actual = {p.name for p in TEMPLATES.glob("*.md")}
    assert expected <= actual, f"missing templates: {expected - actual}"


def test_scripts_exist() -> None:
    for name in ("secret_scan.py", "diff_size_check.py", "validate_autonomous_config.py"):
        assert (SCRIPTS / name).exists(), f"missing script: {name}"


def test_pm_autonomous_command_exists() -> None:
    assert (COMMANDS / "pm-autonomous.md").exists()


def test_pm_autonomous_loop_command_exists() -> None:
    assert (COMMANDS / "pm-autonomous-loop.md").exists()


def test_skill_md_describes_autonomous_mode() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Autonomous mode" in content
    assert "templates/autonomous/" in content
    # Both modes named:
    assert "Human-gated" in content
    assert "Autonomous" in content


def test_cycle_template_mentions_all_phases() -> None:
    content = (TEMPLATES / "cycle.md").read_text()
    for phase in ("Phase 0", "Phase A", "Phase B", "Phase C", "Phase D", "Phase E"):
        assert phase in content, f"cycle.md missing {phase}"


def test_cycle_template_auto_bootstraps_config() -> None:
    """Phase 0 must auto-create autonomous.yaml when missing, never prompt the user.

    The skill's design rule: once invoked, it doesn't ask permission for setup
    decisions the user has already implicitly authorized by running the command.
    """
    content = (TEMPLATES / "cycle.md").read_text()
    assert "MISSING" in content and "bootstrap" in content.lower(), (
        "cycle.md Phase 0 must explicitly handle missing autonomous.yaml by bootstrapping"
    )
    assert "do NOT ask the user" in content or "do NOT prompt" in content.lower(), (
        "cycle.md Phase 0 must explicitly forbid prompting on autonomous.yaml bootstrap"
    )


def test_gate_template_lists_five_self_review_questions() -> None:
    content = (TEMPLATES / "convince-self-gate.md").read_text()
    # Each of the five questions is numbered 1.–5. in spec §3b.
    bullets = re.findall(r"^\d+\.\s+\*\*", content, re.MULTILINE)
    assert len(bullets) >= 5, f"expected >=5 numbered self-review items, got {len(bullets)}"


def test_email_template_has_three_sections() -> None:
    content = (TEMPLATES / "email-format.md").read_text()
    assert "## Hard rules" in content
    assert "## Layout" in content
    assert "## Self-review" in content


def test_pm_autonomous_command_frontmatter() -> None:
    content = (COMMANDS / "pm-autonomous.md").read_text()
    assert content.startswith("---\n")
    assert "description:" in content.split("---", 2)[1]


def test_pm_autonomous_loop_references_loop_skill() -> None:
    content = (COMMANDS / "pm-autonomous-loop.md").read_text()
    assert "/loop" in content or "loop skill" in content.lower()
    assert "stop|pause|halt" in content
