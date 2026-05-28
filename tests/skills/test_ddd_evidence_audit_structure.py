"""Structural invariants for the ddd-evidence-audit skill.

These tests don't exercise behavior — they pin down that the artifacts
exist and contain the load-bearing strings the skill relies on. Drift here
is a bug.
"""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL_DIR = PLUGIN_ROOT / "skills" / "ddd-evidence-audit"
COMMANDS = PLUGIN_ROOT / "commands"


def test_skill_md_exists() -> None:
    assert (SKILL_DIR / "SKILL.md").exists(), "SKILL.md missing for ddd-evidence-audit"


def test_command_file_exists() -> None:
    assert (COMMANDS / "ddd-evidence-audit.md").exists(), "command file missing"


def test_skill_name_in_frontmatter() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    # frontmatter is between first two ---
    fm = content.split("---", 2)[1]
    assert "name: ddd-evidence-audit" in fm


def test_skill_has_inputs_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Inputs" in content


def test_skill_has_procedure_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Procedure" in content


def test_skill_has_evidence_tags() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "documented" in content
    assert "implemented" in content
    assert "assumed" in content


def test_skill_mentions_evidence_inventory() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "evidence inventory" in content.lower()


def test_skill_has_preamble_update_check() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Preamble (run first)" in content
    assert "canopy-update-check.sh" in content


def test_command_has_allowed_tools() -> None:
    content = (COMMANDS / "ddd-evidence-audit.md").read_text()
    assert "allowed-tools" in content


def test_command_has_description() -> None:
    content = (COMMANDS / "ddd-evidence-audit.md").read_text()
    fm = content.split("---", 2)[1]
    assert "description:" in fm
