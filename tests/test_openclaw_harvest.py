"""Tests for the OpenClaw harvester (inventory / compare / bootstrap / reconcile)."""
import pytest

from orchestrator.agent_factory import AgentSpec, create_agent
from orchestrator.openclaw_harvest import (
    HarvestError,
    bootstrap_from_snapshot,
    compare,
    inventory_snapshot,
    port_new_skills,
)


def _fake_openclaw(tmp_path):
    """A minimal OpenClaw workspace snapshot on disk."""
    d = tmp_path / "snap"
    (d / "skills" / "outreach").mkdir(parents=True)
    (d / "skills" / "weekly-digest").mkdir(parents=True)
    (d / "memory").mkdir(parents=True)
    (d / "SOUL.md").write_text("# Soul\nEva is warm, concise, relentless.\n")
    (d / "IDENTITY.md").write_text("# Identity\nEva — partner outreach agent.\n")
    # OpenClaw skill WITHOUT canopy frontmatter (freeform) — name falls back to dir, desc to heading
    (d / "skills" / "outreach" / "SKILL.md").write_text("# Outreach\nDraft warm intros to partners.\n")
    # OpenClaw skill WITH canopy-style frontmatter
    (d / "skills" / "weekly-digest" / "SKILL.md").write_text(
        "---\nname: weekly-digest\ndescription: Summarize the week for stakeholders.\n---\n# Body\n"
    )
    (d / "memory" / "partner-acme.md").write_text("ACME prefers Tuesday calls.\n")
    return d


def test_inventory_parses_persona_skills_memory(tmp_path):
    inv = inventory_snapshot(_fake_openclaw(tmp_path))
    assert inv["has_persona"]
    assert "SOUL.md" in inv["persona"] and "IDENTITY.md" in inv["persona"]
    keys = {s["key"] for s in inv["skills"]}
    assert keys == {"outreach", "weekly-digest"}
    # freeform skill: description falls back to the markdown heading
    outreach = next(s for s in inv["skills"] if s["key"] == "outreach")
    assert "Outreach" in outreach["description"]
    # frontmatter skill: description from frontmatter
    wd = next(s for s in inv["skills"] if s["key"] == "weekly-digest")
    assert "Summarize the week" in wd["description"]
    assert len(inv["memory"]) == 1


def test_inventory_missing_dir_raises(tmp_path):
    with pytest.raises(HarvestError):
        inventory_snapshot(tmp_path / "nope")


def test_compare_no_repo_recommends_bootstrap(tmp_path):
    inv = inventory_snapshot(_fake_openclaw(tmp_path))
    result = compare(inv, None)
    assert result["recommendation"] == "bootstrap"
    assert not result["repo_exists"]
    assert set(result["only_in_openclaw"]) == {"outreach", "weekly-digest"}


def test_compare_existing_repo_finds_novel_skills(tmp_path):
    inv = inventory_snapshot(_fake_openclaw(tmp_path))
    repo = tmp_path / "eva"
    create_agent(AgentSpec(slug="eva", display_name="Eva", mandate="x."), repo)
    # repo has turn + self-review; OpenClaw adds outreach + weekly-digest
    result = compare(inv, repo)
    assert result["recommendation"] == "reconcile"
    assert set(result["only_in_openclaw"]) == {"outreach", "weekly-digest"}
    assert "turn" in result["only_in_repo"]


def test_compare_up_to_date_when_repo_has_all(tmp_path):
    snap = _fake_openclaw(tmp_path)
    repo = tmp_path / "eva"
    create_agent(AgentSpec(slug="eva", display_name="Eva", mandate="x."), repo)
    port_new_skills(inventory_snapshot(snap), repo)        # port everything in
    result = compare(inventory_snapshot(snap), repo)
    assert result["recommendation"] != "bootstrap"
    assert result["only_in_openclaw"] == []


def test_bootstrap_seeds_persona_and_ports_skills(tmp_path):
    inv = inventory_snapshot(_fake_openclaw(tmp_path))
    out = bootstrap_from_snapshot(
        inv, slug="eva", display_name="Eva", mandate="partner outreach.", into=tmp_path / "eva-new",
    )
    repo = tmp_path / "eva-new"
    assert set(out["ported_skills"]) == {"outreach", "weekly-digest"}
    assert (repo / "skills" / "outreach" / "SKILL.md").exists()
    # factory skills survive (not clobbered)
    assert (repo / "skills" / "turn" / "SKILL.md").exists()
    # persona seeded with the OpenClaw soul/identity
    persona = (repo / "persona.md").read_text()
    assert "Ported from the OpenClaw" in persona and "relentless" in persona


def test_port_new_skills_never_clobbers(tmp_path):
    inv = inventory_snapshot(_fake_openclaw(tmp_path))
    repo = tmp_path / "eva"
    create_agent(AgentSpec(slug="eva", display_name="Eva", mandate="x."), repo)
    # pre-existing 'outreach' with custom content must NOT be overwritten
    (repo / "skills" / "outreach").mkdir(parents=True)
    (repo / "skills" / "outreach" / "SKILL.md").write_text("CUSTOM — keep me\n")
    ported = port_new_skills(inv, repo)
    assert "outreach" not in ported and "weekly-digest" in ported
    assert (repo / "skills" / "outreach" / "SKILL.md").read_text() == "CUSTOM — keep me\n"
