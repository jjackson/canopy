"""Structural invariants for the ddd-why-eval skill (SP1.4)."""
from __future__ import annotations

from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL_DIR = PLUGIN_ROOT / "skills" / "ddd-why-eval"
COMMANDS = PLUGIN_ROOT / "commands"
RUBRIC_PATH = SKILL_DIR / "rubric.yaml"

EXPECTED_DIMS = {
    "problem_clarity",
    "rationale_soundness",
    "evidence_sufficiency",
    "gap_honesty",
    "user_narrative_strength",
}


def test_skill_md_exists() -> None:
    assert (SKILL_DIR / "SKILL.md").exists(), "SKILL.md missing for ddd-why-eval"


def test_rubric_yaml_exists() -> None:
    assert RUBRIC_PATH.exists(), "rubric.yaml missing for ddd-why-eval"


def test_command_file_exists() -> None:
    assert (COMMANDS / "ddd-why-eval.md").exists(), "command file missing"


def test_skill_name_in_frontmatter() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    fm = content.split("---", 2)[1]
    assert "name: ddd-why-eval" in fm


def test_skill_has_preamble_update_check() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Preamble (run first)" in content
    assert "canopy-update-check.sh" in content


def test_skill_has_qa_gate_sentence() -> None:
    """Skill must gate on ddd-why-qa result."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "If ddd-why-qa returned verdict: fail, skip this eval." in content


def test_skill_emits_verdict_shape() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    # Must reference the visual-judge verdict shape fields
    assert "verdict" in content
    assert "fix_recommendation" in content


def test_rubric_has_five_dimensions() -> None:
    rubric = yaml.safe_load(RUBRIC_PATH.read_text())
    dims = {d["id"] for d in rubric["dimensions"]}
    assert dims == EXPECTED_DIMS, f"Expected dims {EXPECTED_DIMS}, got {dims}"


def test_rubric_weights_sum_to_one() -> None:
    rubric = yaml.safe_load(RUBRIC_PATH.read_text())
    total = sum(d["weight"] for d in rubric["dimensions"])
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_rubric_each_dim_has_anchor() -> None:
    rubric = yaml.safe_load(RUBRIC_PATH.read_text())
    for dim in rubric["dimensions"]:
        assert "anchor" in dim, f"Dimension '{dim['id']}' missing 'anchor'"
        assert dim["anchor"], f"Dimension '{dim['id']}' has empty anchor"


def test_rubric_each_dim_has_default_score() -> None:
    rubric = yaml.safe_load(RUBRIC_PATH.read_text())
    for dim in rubric["dimensions"]:
        assert "default_score" in dim, f"Dimension '{dim['id']}' missing 'default_score'"
        assert dim["default_score"] == 3, (
            f"Dimension '{dim['id']}' default_score should be 3, got {dim['default_score']}"
        )


def test_rubric_has_overall_rule_lowest() -> None:
    rubric = yaml.safe_load(RUBRIC_PATH.read_text())
    assert rubric.get("overall_rule") == "lowest", (
        f"overall_rule should be 'lowest', got {rubric.get('overall_rule')}"
    )


def test_command_has_description() -> None:
    content = (COMMANDS / "ddd-why-eval.md").read_text()
    fm = content.split("---", 2)[1]
    assert "description:" in fm


def test_command_has_allowed_tools() -> None:
    content = (COMMANDS / "ddd-why-eval.md").read_text()
    assert "allowed-tools" in content
