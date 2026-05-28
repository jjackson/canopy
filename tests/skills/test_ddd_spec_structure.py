"""Structural invariants for the ddd-spec skill (SP2.1)."""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL_DIR = PLUGIN_ROOT / "skills" / "ddd-spec"
COMMANDS = PLUGIN_ROOT / "commands"


def test_skill_md_exists() -> None:
    assert (SKILL_DIR / "SKILL.md").exists(), "SKILL.md missing for ddd-spec"


def test_command_file_exists() -> None:
    assert (COMMANDS / "ddd-spec.md").exists(), "command file missing for ddd-spec"


def test_skill_name_in_frontmatter() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    fm = content.split("---", 2)[1]
    assert "name: ddd-spec" in fm


def test_skill_has_preamble_update_check() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Preamble (run first)" in content
    assert "canopy-update-check.sh" in content


def test_skill_has_procedure_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Procedure" in content


def test_skill_mentions_concept_claim() -> None:
    """concept_claim is a required per-scene DDD key."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "concept_claim" in content


def test_skill_mentions_provenance() -> None:
    """provenance links each scene to a why_brief spine item."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "provenance" in content


def test_skill_mentions_design_intent() -> None:
    """design_intent is the per-scene design decision under test."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "design_intent" in content


def test_skill_mentions_why_brief() -> None:
    """Spec is authored FROM the why_brief."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "why_brief" in content


def test_skill_invokes_validator() -> None:
    """Must tell the agent to run the structural validator."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "scripts.ddd.validate" in content or "ddd.validate" in content


def test_skill_mentions_spec_qa() -> None:
    """Must tell the agent to also run spec_qa after validate passes."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "spec_qa" in content


def test_skill_mentions_runnable_walkthrough() -> None:
    """The output must remain a runnable canopy walkthrough spec."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    # Must say something about it staying a runnable walkthrough
    assert "walkthrough" in content
    assert "runnable" in content or "canopy walkthrough" in content


def test_skill_mentions_base_url() -> None:
    """base_url is a required canopy walkthrough key."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "base_url" in content


def test_skill_mentions_narrative() -> None:
    """narrative is a required canopy walkthrough key."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "narrative" in content


def test_skill_mentions_personas() -> None:
    """personas is a required canopy walkthrough key."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "personas" in content


def test_skill_mentions_falsifiable() -> None:
    """concept_claim must be falsifiable — skill must explain this."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "falsifiable" in content.lower()


def test_command_has_description() -> None:
    content = (COMMANDS / "ddd-spec.md").read_text()
    fm = content.split("---", 2)[1]
    assert "description:" in fm


def test_command_has_allowed_tools() -> None:
    content = (COMMANDS / "ddd-spec.md").read_text()
    assert "allowed-tools" in content
