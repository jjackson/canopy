"""Structural invariants for the ddd-spec-qa skill (SP2.2)."""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL_DIR = PLUGIN_ROOT / "skills" / "ddd-spec-qa"
COMMANDS = PLUGIN_ROOT / "commands"
SCRIPTS_DDD = Path(__file__).parent.parent.parent / "scripts" / "ddd"


def test_skill_md_exists() -> None:
    assert (SKILL_DIR / "SKILL.md").exists(), "SKILL.md missing for ddd-spec-qa"


def test_command_file_exists() -> None:
    assert (COMMANDS / "ddd-spec-qa.md").exists(), "command file missing for ddd-spec-qa"


def test_spec_qa_module_exists() -> None:
    assert (SCRIPTS_DDD / "spec_qa.py").exists(), "scripts/ddd/spec_qa.py is missing"


def test_skill_name_in_frontmatter() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    fm = content.split("---", 2)[1]
    assert "name: ddd-spec-qa" in fm


def test_skill_has_preamble_update_check() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Preamble (run first)" in content
    assert "canopy-update-check.sh" in content


def test_skill_invokes_spec_qa_module() -> None:
    """Must tell the agent to run python -m scripts.ddd.spec_qa."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "scripts.ddd.spec_qa" in content


def test_skill_mentions_verdict_shape() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "verdict" in content
    assert "pass" in content
    assert "fail" in content


def test_skill_mentions_blocking_reason() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "blocking_reason" in content


def test_skill_mentions_concept_claim() -> None:
    """concept_claim falsifiability is the QA-specific check."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "concept_claim" in content


def test_skill_mentions_falsifiable() -> None:
    """Skill must explain the falsifiability rule."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "falsifiable" in content.lower()


def test_skill_mentions_banned_phrases() -> None:
    """Skill must name at least some banned phrases."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    # At least one of the banned phrases must be mentioned
    banned = ["world-class", "seamless", "powerful", "robust", "best-in-class"]
    assert any(phrase in content for phrase in banned), (
        "SKILL.md must name at least one banned marketing phrase"
    )


def test_skill_mentions_delegation_to_validate() -> None:
    """Skill must document that Layer 1 delegates to validate()."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    # Must mention delegation to validate (so provenance/persona checks aren't duplicated)
    assert "validate" in content


def test_skill_is_gate_before_concept_judge() -> None:
    """Skill must declare itself as the gate before ddd-concept-eval."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "ddd-concept-eval" in content


def test_skill_mentions_real_falsifiability_rules() -> None:
    """Skill must mention the actual rules: banned phrases + minimum length (not verb detection)."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    # Must mention banned-phrase rule
    assert "banned" in content.lower() or "marketing" in content.lower(), (
        "SKILL.md must document the banned marketing phrases rule"
    )
    # Must mention minimum-length rule
    assert "5 words" in content or "fewer than 5" in content or "minimum" in content.lower(), (
        "SKILL.md must document the minimum-length rule"
    )


def test_command_has_description() -> None:
    content = (COMMANDS / "ddd-spec-qa.md").read_text()
    fm = content.split("---", 2)[1]
    assert "description:" in fm


def test_command_has_allowed_tools() -> None:
    content = (COMMANDS / "ddd-spec-qa.md").read_text()
    assert "allowed-tools" in content


def test_spec_qa_delegates_to_validate() -> None:
    """spec_qa.py must import from scripts.ddd.validate — proves delegation."""
    content = (SCRIPTS_DDD / "spec_qa.py").read_text()
    assert "from scripts.ddd.validate import validate" in content


def test_spec_qa_returns_verdict() -> None:
    """spec_qa.py must import and return Verdict."""
    content = (SCRIPTS_DDD / "spec_qa.py").read_text()
    assert "Verdict" in content
    assert "verdict" in content


def test_spec_qa_has_main_cli() -> None:
    """spec_qa.py must have a __main__ CLI entry point."""
    content = (SCRIPTS_DDD / "spec_qa.py").read_text()
    assert '__name__ == "__main__"' in content or "__name__ == '__main__'" in content


def test_spec_qa_cli_exit_codes() -> None:
    """spec_qa.py must document exit codes 0/1/2."""
    content = (SCRIPTS_DDD / "spec_qa.py").read_text()
    assert "sys.exit(0)" in content
    assert "sys.exit(1)" in content
    assert "sys.exit(2)" in content
