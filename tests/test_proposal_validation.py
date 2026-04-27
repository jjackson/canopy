"""Tests for the new_skill overlap-drop logic in _validate_proposals."""
from orchestrator.cli import _validate_proposals


REGISTRY = {
    "version": "1.0",
    "servers": [],
    "tools": [],
    "workflows": [],
}


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
        result = _validate_proposals(proposals, REGISTRY, catalog)
        assert result == []

    def test_keeps_novel_skill(self):
        catalog = [_catalog_entry("canopy:doctor")]
        proposals = [_proposal(action="Build canopy:project-status skill that surveys worktrees")]
        result = _validate_proposals(proposals, REGISTRY, catalog)
        assert len(result) == 1

    def test_drops_hyphenated_user_skill_match(self):
        catalog = [_catalog_entry("context-restore", scope="user")]
        proposals = [_proposal(action="Add a context-restore helper for resume after vacation")]
        result = _validate_proposals(proposals, REGISTRY, catalog)
        assert result == []

    def test_does_not_drop_when_catalog_empty(self):
        proposals = [_proposal(action="Add canopy:doctor diagnostic")]
        result = _validate_proposals(proposals, REGISTRY, skill_catalog=[])
        assert len(result) == 1

    def test_does_not_drop_non_skill_proposals(self):
        catalog = [_catalog_entry("canopy:doctor")]
        proposals = [_proposal(
            type="tool_improvement",
            action="Improve canopy:doctor checks",
        )]
        result = _validate_proposals(proposals, REGISTRY, catalog)
        # tool_improvement should pass through even if name overlaps
        assert len(result) == 1

    def test_mixed_proposals(self):
        catalog = [_catalog_entry("canopy:doctor")]
        proposals = [
            _proposal(action="Add canopy:doctor diagnostic"),         # drop
            _proposal(action="Build canopy:project-status skill"),     # keep
            _proposal(action="Add canopy:auth-preflight"),             # keep (not in catalog)
        ]
        result = _validate_proposals(proposals, REGISTRY, catalog)
        assert len(result) == 2
        actions = [p["action"] for p in result]
        assert "Add canopy:doctor diagnostic" not in actions
