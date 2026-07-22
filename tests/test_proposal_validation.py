"""Tests for the new_skill overlap-drop logic in _validate_proposals."""
from orchestrator.cli import _validate_proposals


def _proposal(**kwargs) -> dict:
    base = {
        "type": "new_skill",
        "action": "Create a new skill",
        "target_repo": "~/.claude/skills/",
        "ownership": "self",
        "motivation": "Because.",
        "observation_id": "abc",
        "complexity": "low",
        "verification": {"confidence": "medium"},
    }
    base.update(kwargs)
    return base


def _catalog_entry(qualified: str, scope: str = "plugin") -> dict:
    name = qualified.split(":", 1)[-1]
    return {
        "name": name,
        "qualified": qualified,
        "scope": scope,
        "source": qualified.split(":", 1)[0] if ":" in qualified else "user",
        "description": "test entry",
        "path": f"/fake/{qualified}/SKILL.md",
    }


class TestNewSkillOverlapDrop:
    def test_drops_overlapping_qualified_skill(self):
        catalog = [_catalog_entry("canopy:doctor")]
        proposals = [_proposal(action="Add canopy:doctor diagnostic for plugin health")]
        kept, dropped = _validate_proposals(proposals, catalog)
        assert kept == []
        assert len(dropped) == 1
        assert "_dropped" in dropped[0]

    def test_keeps_novel_skill(self):
        catalog = [_catalog_entry("canopy:doctor")]
        proposals = [_proposal(action="Build canopy:project-status skill that surveys worktrees")]
        kept, dropped = _validate_proposals(proposals, catalog)
        assert len(kept) == 1
        assert dropped == []

    def test_drops_hyphenated_user_skill_match(self):
        catalog = [_catalog_entry("context-restore", scope="user")]
        proposals = [_proposal(action="Add a context-restore helper for resume after vacation")]
        kept, dropped = _validate_proposals(proposals, catalog)
        assert kept == []
        assert len(dropped) == 1

    def test_does_not_drop_when_catalog_empty(self):
        proposals = [_proposal(action="Add canopy:doctor diagnostic")]
        kept, dropped = _validate_proposals(proposals, skill_catalog=[])
        assert len(kept) == 1
        assert dropped == []

    def test_does_not_drop_non_skill_proposals(self):
        catalog = [_catalog_entry("canopy:doctor")]
        proposals = [_proposal(
            type="tool_improvement",
            action="Improve canopy:doctor checks",
        )]
        kept, dropped = _validate_proposals(proposals, catalog)
        assert len(kept) == 1
        assert dropped == []

    def test_mixed_proposals(self):
        catalog = [_catalog_entry("canopy:doctor")]
        proposals = [
            _proposal(action="Add canopy:doctor diagnostic"),         # drop
            _proposal(action="Build canopy:project-status skill"),     # keep
            _proposal(action="Add canopy:auth-preflight"),             # keep (not in catalog)
        ]
        kept, dropped = _validate_proposals(proposals, catalog)
        assert len(kept) == 2
        assert len(dropped) == 1
        actions = [p["action"] for p in kept]
        assert "Add canopy:doctor diagnostic" not in actions
