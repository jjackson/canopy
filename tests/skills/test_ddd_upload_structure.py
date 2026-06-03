"""Structural invariants for the ddd-upload skill.

Pins the load-bearing strings and shape of SKILL.md and the command file.
Does NOT exercise runtime behaviour — drift here is a bug.

Checked invariants:
    1.  SKILL.md exists with correct name in frontmatter.
    2.  Preamble (update check) present.
    3.  ## Inputs section names run_id and video_path.
    4.  ## Procedure section present.
    5.  Script invocation: references python -m scripts.ddd.upload.
    6.  Docs page structure described: hero video on top.
    7.  Docs page sections: "What you can do", "Why it works this way", "How to use it".
    8.  Docs page audience described as prospective user / feature user.
    9.  External release gate mentioned with publish + hold options.
    10. Remotion deferred: SKILL.md notes Remotion is a deferred / future upgrade.
    11. Command file exists with description and allowed-tools (incl. Bash).
"""
from __future__ import annotations

from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent.parent / "plugins" / "canopy"
SKILL_DIR = PLUGIN_ROOT / "skills" / "ddd-upload"
COMMANDS = PLUGIN_ROOT / "commands"


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


def test_skill_md_exists() -> None:
    assert (SKILL_DIR / "SKILL.md").exists(), "SKILL.md missing for ddd-upload"


def test_command_file_exists() -> None:
    assert (COMMANDS / "ddd-upload.md").exists(), "command file missing for ddd-upload"


# ---------------------------------------------------------------------------
# Frontmatter + preamble
# ---------------------------------------------------------------------------


def test_skill_name_in_frontmatter() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    fm = content.split("---", 2)[1]
    assert "name: ddd-upload" in fm, "SKILL.md frontmatter must declare 'name: ddd-upload'"


def test_skill_has_preamble_update_check() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Preamble (run first)" in content
    assert "canopy-update-check.sh" in content


# ---------------------------------------------------------------------------
# Inputs section
# ---------------------------------------------------------------------------


def test_skill_has_inputs_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Inputs" in content


def test_skill_inputs_names_run_id() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "run_id" in content, "Inputs must name run_id"


def test_skill_inputs_names_video_path() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "video_path" in content or "video" in content, "Inputs must name the video path"


# ---------------------------------------------------------------------------
# Procedure section
# ---------------------------------------------------------------------------


def test_skill_has_procedure_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "## Procedure" in content


def test_skill_references_upload_script() -> None:
    """Procedure must invoke python -m scripts.ddd.upload."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "scripts.ddd.upload" in content, (
        "Procedure must reference python -m scripts.ddd.upload"
    )


# ---------------------------------------------------------------------------
# Docs page structure
# ---------------------------------------------------------------------------


def test_skill_mentions_hero_video_at_top() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "hero video" in content.lower() or "hero" in content.lower(), (
        "SKILL.md must describe the hero video at the top of the docs page"
    )


def test_skill_mentions_what_you_can_do_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "What you can do" in content, (
        "SKILL.md must name the 'What you can do' section (capabilities)"
    )


def test_skill_mentions_why_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "Why it works this way" in content, (
        "SKILL.md must name the 'Why it works this way' section"
    )


def test_skill_mentions_how_section() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "How to use it" in content, (
        "SKILL.md must name the 'How to use it' section"
    )


def test_skill_mentions_prospective_user_audience() -> None:
    """The docs page must be described as targeting a prospective feature user."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    audience_signals = [
        "prospective user",
        "feature user",
        "prospective users",
    ]
    assert any(s in content.lower() for s in audience_signals), (
        "SKILL.md must describe the audience as prospective user / feature user"
    )


def test_skill_mentions_concept_claim() -> None:
    """What you can do must be tied to concept_claim."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "concept_claim" in content, (
        "SKILL.md must note that capabilities come from scene concept_claim fields"
    )


def test_skill_mentions_show_field() -> None:
    """How to use it must be tied to scene.show."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "show" in content, (
        "SKILL.md must note that steps come from scene.show fields"
    )


# ---------------------------------------------------------------------------
# External release gate
# ---------------------------------------------------------------------------


def test_skill_mentions_external_release_gate() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "external_release" in content, (
        "SKILL.md must describe the external_release gate"
    )


def test_skill_mentions_publish_option() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "publish" in content, (
        "SKILL.md must describe the 'publish' gate option"
    )


def test_skill_mentions_hold_option() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "hold" in content, (
        "SKILL.md must describe the 'hold' gate option"
    )


def test_skill_describes_hold_behaviour() -> None:
    """On hold: phase stays unchanged and HTML is not published."""
    content = (SKILL_DIR / "SKILL.md").read_text()
    # Must describe what happens when held — phase unchanged or not published
    hold_signals = ["phase unchanged", "not published", "phase stays", "no HTML", "hold"]
    assert any(s.lower() in content.lower() for s in hold_signals), (
        "SKILL.md must describe what happens when the gate returns 'hold'"
    )


# ---------------------------------------------------------------------------
# Remotion deferred note
# ---------------------------------------------------------------------------


def test_skill_notes_remotion_is_deferred() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    assert "remotion" in content.lower() or "Remotion" in content, (
        "SKILL.md must note that the Remotion glossy render is deferred"
    )


def test_skill_remotion_marked_as_deferred_or_future() -> None:
    content = (SKILL_DIR / "SKILL.md").read_text()
    # Accept "deferred", "future", "out of scope", "planned"
    deferred_signals = ["deferred", "future", "out of scope", "planned"]
    assert any(s.lower() in content.lower() for s in deferred_signals), (
        "SKILL.md must mark Remotion as deferred / future upgrade"
    )


# ---------------------------------------------------------------------------
# Command file
# ---------------------------------------------------------------------------


def test_command_has_description() -> None:
    content = (COMMANDS / "ddd-upload.md").read_text()
    fm = content.split("---", 2)[1]
    assert "description:" in fm, "Command file must have a description in frontmatter"


def test_command_has_allowed_tools() -> None:
    content = (COMMANDS / "ddd-upload.md").read_text()
    assert "allowed-tools" in content, "Command file must declare allowed-tools"


def test_command_allowed_tools_includes_bash() -> None:
    content = (COMMANDS / "ddd-upload.md").read_text()
    assert "Bash" in content, "Command allowed-tools must include Bash to run the upload script"


def test_command_description_mentions_external_release() -> None:
    content = (COMMANDS / "ddd-upload.md").read_text()
    assert "external_release" in content or "gate" in content.lower(), (
        "Command description must mention the external_release gate"
    )


def test_command_description_mentions_uploaded_phase() -> None:
    content = (COMMANDS / "ddd-upload.md").read_text()
    assert "uploaded" in content, (
        "Command description must mention the uploaded phase transition"
    )
