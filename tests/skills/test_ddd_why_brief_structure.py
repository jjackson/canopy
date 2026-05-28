"""Structural invariants for the ddd-why-brief skill."""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL_DIR = PLUGIN_ROOT / "skills" / "ddd-why-brief"
COMMANDS = PLUGIN_ROOT / "commands"


def test_skill_md_exists() -> None:
    assert (SKILL_DIR / "SKILL.md").exists(), "SKILL.md missing for ddd-why-brief"


def test_command_file_exists() -> None:
    assert (COMMANDS / "ddd-why-brief.md").exists(), "command file missing"


def test_skill_name_in_frontmatter() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    fm = content.split("---", 2)[1]
    assert "name: ddd-why-brief" in fm


def test_skill_has_preamble_update_check() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Preamble (run first)" in content
    assert "canopy-update-check.sh" in content


def test_skill_has_procedure_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Procedure" in content


def test_skill_mentions_gap_types() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "RESEARCH" in content
    assert "CAPABILITY" in content
    assert "DECISION" in content


def test_skill_mentions_provenance() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "provenance" in content


def test_skill_invokes_validator() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "scripts.ddd.validate" in content or "ddd.validate" in content


def test_skill_mentions_gap_type_routing() -> None:
    """Must include the canonical sentence about gap routing."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "DECISION gaps" in content
    assert "CAPABILITY gaps" in content
    assert "RESEARCH gaps" in content


def test_command_has_description() -> None:
    content = (COMMANDS / "ddd-why-brief.md").read_text()
    fm = content.split("---", 2)[1]
    assert "description:" in fm


def test_command_has_allowed_tools() -> None:
    content = (COMMANDS / "ddd-why-brief.md").read_text()
    assert "allowed-tools" in content
