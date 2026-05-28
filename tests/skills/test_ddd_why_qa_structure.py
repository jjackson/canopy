"""Structural invariants for the ddd-why-qa skill (SP1.3)."""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL_DIR = PLUGIN_ROOT / "skills" / "ddd-why-qa"
COMMANDS = PLUGIN_ROOT / "commands"


def test_skill_md_exists() -> None:
    assert (SKILL_DIR / "SKILL.md").exists(), "SKILL.md missing for ddd-why-qa"


def test_command_file_exists() -> None:
    assert (COMMANDS / "ddd-why-qa.md").exists(), "command file missing"


def test_skill_name_in_frontmatter() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    fm = content.split("---", 2)[1]
    assert "name: ddd-why-qa" in fm


def test_skill_has_preamble_update_check() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Preamble (run first)" in content
    assert "canopy-update-check.sh" in content


def test_skill_invokes_why_qa_module() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "scripts.ddd.why_qa" in content


def test_skill_mentions_verdict_shape() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "verdict" in content
    assert "pass" in content
    assert "fail" in content


def test_skill_mentions_blocking_reason() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "blocking_reason" in content


def test_command_has_description() -> None:
    content = (COMMANDS / "ddd-why-qa.md").read_text()
    fm = content.split("---", 2)[1]
    assert "description:" in fm


def test_command_has_allowed_tools() -> None:
    content = (COMMANDS / "ddd-why-qa.md").read_text()
    assert "allowed-tools" in content
