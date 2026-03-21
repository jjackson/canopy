import yaml
import pytest
from orchestrator.proposer import (
    build_proposal_prompt,
    parse_proposal_output,
)


class TestBuildProposalPrompt:
    def test_returns_string(self):
        obs = [{"type": "gap", "description": "test", "id": "abc"}]
        prompt = build_proposal_prompt(obs, registry_summary="test registry")
        assert isinstance(prompt, str)

    def test_includes_observations(self):
        obs = [{"type": "gap", "description": "No training tool", "id": "abc"}]
        prompt = build_proposal_prompt(obs, registry_summary="test")
        assert "training tool" in prompt.lower()

    def test_includes_registry(self):
        obs = [{"type": "gap", "description": "test", "id": "abc"}]
        prompt = build_proposal_prompt(obs, registry_summary="## Server: connect-search")
        assert "connect-search" in prompt


class TestParseProposalOutput:
    def test_parses_valid_yaml_list(self):
        output = yaml.dump([{
            "type": "new_tool",
            "action": "Create training tool",
            "target_repo": "~/emdash-projects/connect-labs",
            "ownership": "self",
            "motivation": "Needed for training",
            "observation_id": "abc",
            "complexity": "medium",
        }])
        result = parse_proposal_output(output)
        assert len(result) == 1
        assert result[0]["type"] == "new_tool"

    def test_empty_list(self):
        assert parse_proposal_output("[]") == []

    def test_handles_invalid(self):
        assert parse_proposal_output("not yaml!!!") == []

    def test_handles_markdown_fence(self):
        output = "```yaml\n- type: new_tool\n  action: test\n```"
        result = parse_proposal_output(output)
        assert len(result) == 1
