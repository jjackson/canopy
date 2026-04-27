"""Detect and guard against command/skill name collisions.

Background: When `plugins/canopy/commands/<name>.md` and
`plugins/canopy/skills/<name>/SKILL.md` both exist, the Skill tool resolves
`canopy:<name>` to the slash command file and the SKILL.md never lands in
context. The command then has to read SKILL.md from disk explicitly
(Pattern B) — otherwise the agent improvises from memory.

These tests enforce: every colliding command must reference its
sibling SKILL.md file path so it can read it via the Read tool.
"""

from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "plugins" / "canopy"
COMMANDS_DIR = PLUGIN_ROOT / "commands"
SKILLS_DIR = PLUGIN_ROOT / "skills"


def _find_collisions() -> list[str]:
    command_names = {p.stem for p in COMMANDS_DIR.glob("*.md")}
    skill_names = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    return sorted(command_names & skill_names)


COLLIDING_NAMES = _find_collisions()


def test_collision_set_is_nonempty_or_skills_dir_is_empty():
    """Sanity check: if there are skills and commands at all, we expect to know
    about collisions. This guards against the test silently passing because
    glob returned nothing."""
    has_commands = any(COMMANDS_DIR.glob("*.md"))
    has_skills = any(p.is_dir() for p in SKILLS_DIR.iterdir())
    assert has_commands and has_skills, (
        "Expected both commands/ and skills/ directories to be populated"
    )


@pytest.mark.parametrize("name", COLLIDING_NAMES)
def test_colliding_command_reads_skill_md_from_disk(name):
    """Every command that shares a name with a skill must reference SKILL.md
    so the agent reads the actual skill content rather than re-serving the
    command body."""
    command_path = COMMANDS_DIR / f"{name}.md"
    body = command_path.read_text()

    assert "SKILL.md" in body, (
        f"Command `{name}` collides with skill of the same name but does not "
        f"reference SKILL.md. The Skill tool will silently re-serve the command "
        f"body instead of the skill. Fix: convert {command_path} to Pattern B "
        f"(read SKILL.md from disk via installed_plugins.json, then Read it)."
    )

    assert f"skills/{name}/SKILL.md" in body, (
        f"Command `{name}` references SKILL.md but not the expected path "
        f"`skills/{name}/SKILL.md`. Make sure the command points at its own "
        f"sibling skill, not a different one."
    )
