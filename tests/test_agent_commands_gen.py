"""Tests for the entry-point-skill command generator (canopy agent stamp-commands)."""
from pathlib import Path

from orchestrator.agent_commands_gen import (
    skill_description,
    plan_commands,
    stamp_commands,
)


def _skill(repo: Path, name: str, description: str) -> None:
    d = repo / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: >\n  {description}\n---\n\n# {name}\n"
    )


def _agent_repo(tmp_path: Path) -> Path:
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "agent.json").write_text('{"display_name": "Testy"}')
    return tmp_path


# --- description condensing -----------------------------------------------------------

def test_skill_description_drops_use_when_tail():
    md = (
        "---\nname: x\ndescription: >\n  Draft a thing from live data.\n"
        "  Use when asked to \"draft a thing\".\n---\n"
    )
    assert skill_description(md) == "Draft a thing from live data."


def test_skill_description_never_truncates_mid_word():
    long = "word " * 60  # ~300 chars, no sentence boundary
    md = f"---\nname: x\ndescription: >\n  {long.strip()}\n---\n"
    out = skill_description(md)
    assert len(out) <= 201
    assert not out[:-1].endswith(" ")           # trimmed
    assert " wor." not in out and out.endswith(".")  # not cut mid-word


# --- promotion policy -----------------------------------------------------------------

def test_promotes_domain_skills_only(tmp_path):
    repo = _agent_repo(tmp_path)
    _skill(repo, "conduct", "Conduct the fleet.")
    _skill(repo, "turn", "The turn orchestrator.")            # framework
    _skill(repo, "agent-turn-review", "Pre-send gate.")      # framework
    _skill(repo, "task-tracker", "Board state.")             # framework
    _skill(repo, "idea-to-pdd-eval", "Grade a PDD.")         # grader
    _skill(repo, "solicitation-review-qa", "QA the review.") # grader

    plan = plan_commands(repo)
    created = {c["skill"] for c in plan["create"]}
    skipped = {s["skill"]: s["reason"] for s in plan["skip"]}

    assert created == {"conduct"}
    assert skipped["turn"] == "framework"
    assert skipped["agent-turn-review"] == "framework"
    assert skipped["idea-to-pdd-eval"] == "grader"
    assert skipped["solicitation-review-qa"] == "grader"


def test_exclude_file_keeps_skill_as_skill_only(tmp_path):
    repo = _agent_repo(tmp_path)
    _skill(repo, "fleet-review", "Umbrella review.")
    _skill(repo, "fleet-turn-readiness", "A sub-lens.")
    (repo / "commands").mkdir()
    (repo / "commands" / ".exclude").write_text(
        "# sub-lenses\nfleet-turn-readiness\n"
    )

    plan = plan_commands(repo)
    assert {c["skill"] for c in plan["create"]} == {"fleet-review"}
    assert {s["skill"]: s["reason"] for s in plan["skip"]}["fleet-turn-readiness"] == "excluded"


def test_stamp_is_idempotent_and_additive(tmp_path):
    repo = _agent_repo(tmp_path)
    _skill(repo, "conduct", "Conduct the fleet.")

    first = stamp_commands(repo)
    assert [c["skill"] for c in first["create"]] == ["conduct"]
    body = (repo / "commands" / "conduct.md").read_text()
    assert "Run Testy's `conduct` procedure." in body
    assert "$ARGUMENTS" in body
    assert body.startswith("---\ndescription: Conduct the fleet.\n")

    # a hand-edit must survive a re-run (never clobbered)
    (repo / "commands" / "conduct.md").write_text("HAND EDITED")
    second = stamp_commands(repo)
    assert second["create"] == []
    assert {s["skill"]: s["reason"] for s in second["skip"]}["conduct"] == "exists"
    assert (repo / "commands" / "conduct.md").read_text() == "HAND EDITED"


def test_no_skills_dir_is_safe(tmp_path):
    plan = plan_commands(tmp_path)
    assert plan["create"] == [] and plan["skip"] == []
