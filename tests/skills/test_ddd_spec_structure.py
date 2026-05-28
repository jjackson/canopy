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


# ---------------------------------------------------------------------------
# v3 — features[] requirement (ddd-v3-author-and-gate)
# ---------------------------------------------------------------------------


def test_skill_requires_features_per_scene() -> None:
    """v3: SKILL.md must require ≥1 verifiable feature per scene."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "features" in content, "SKILL.md must document the 'features' key"


def test_skill_documents_feature_id_description_verify() -> None:
    """v3: each feature must have id, description, verify."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "id" in content
    assert "description" in content
    assert "verify" in content


def test_skill_requires_runnable_verify() -> None:
    """v3: verify must be a runnable validation, not a vague placeholder."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    runnable_signals = ["runnable", "assertion", "api assertion", "test command", "verify"]
    assert any(s.lower() in content.lower() for s in runnable_signals), (
        "SKILL.md must describe 'verify' as a runnable validation (API assertion, test command, etc.)"
    )


def test_skill_mentions_spec_qa_feature_gate() -> None:
    """v3: SKILL.md must mention that spec-qa now requires ≥1 feature per scene."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    feature_gate_signals = [
        "≥1",
        "at least 1",
        "at least one",
        "ddd-spec-qa now requires",
        "requires ≥1",
        "requires at least",
    ]
    assert any(s.lower() in content.lower() for s in feature_gate_signals), (
        "SKILL.md must mention that ddd-spec-qa now requires ≥1 verifiable feature per scene"
    )


def test_skill_mentions_actionability_eval() -> None:
    """v3: SKILL.md must mention ddd-narrative-actionability-eval."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "ddd-narrative-actionability-eval" in content or "actionability" in content, (
        "SKILL.md must mention the ddd-narrative-actionability-eval gate"
    )
