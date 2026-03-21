import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from orchestrator.implementer import (
    build_implementation_prompt,
    resolve_repo_path,
    run_implementation,
)


class TestBuildImplementationPrompt:
    def test_returns_string(self):
        prompt = build_implementation_prompt(
            proposal={"type": "new_tool", "action": "Create tool X"},
            observation={"type": "gap", "description": "Missing tool X"},
            registry_summary="test registry",
        )
        assert isinstance(prompt, str)

    def test_includes_proposal(self):
        prompt = build_implementation_prompt(
            proposal={"type": "new_tool", "action": "Create generate_training_manual"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert "generate_training_manual" in prompt

    def test_includes_observation(self):
        prompt = build_implementation_prompt(
            proposal={"type": "new_tool", "action": "test"},
            observation={"type": "gap", "description": "No training material tool"},
            registry_summary="test",
        )
        assert "training material" in prompt.lower()


class TestResolveRepoPath:
    def test_expands_tilde(self):
        path = resolve_repo_path("~/emdash-projects/connect-labs")
        assert "~" not in str(path)
        assert "emdash-projects" in str(path)

    def test_returns_path_object(self):
        path = resolve_repo_path("~/emdash-projects/connect-labs")
        assert isinstance(path, Path)

    def test_absolute_path_unchanged(self):
        path = resolve_repo_path("/tmp/test-repo")
        assert path == Path("/tmp/test-repo").resolve()


class TestRunImplementation:
    def test_external_ownership_skips(self):
        result = run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": "/tmp/x", "ownership": "external"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert result["success"] is False
        assert "registry-only" in result["error"]

    def test_missing_repo_returns_error(self):
        result = run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": "/nonexistent/repo", "ownership": "self"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert result["success"] is False
        assert "not found" in result["error"]

    @patch("orchestrator.implementer.subprocess.run")
    def test_success_returns_output(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="Implemented!", stderr="")
        result = run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": str(tmp_path), "ownership": "self"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert result["success"] is True
        assert result["output"] == "Implemented!"

    @patch("orchestrator.implementer.subprocess.run")
    def test_failure_returns_error(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Tests failed")
        result = run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": str(tmp_path), "ownership": "self"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert result["success"] is False
        assert "Tests failed" in result["error"]

    @patch("orchestrator.implementer.subprocess.run")
    def test_timeout_returns_error(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=600)
        result = run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": str(tmp_path), "ownership": "self"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        assert result["success"] is False
        assert "timed out" in result["error"]

    @patch("orchestrator.implementer.subprocess.run")
    def test_team_ownership_appends_pr_instruction(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="Done", stderr="")
        run_implementation(
            proposal={"type": "new_tool", "action": "test", "target_repo": str(tmp_path), "ownership": "team"},
            observation={"type": "gap", "description": "test"},
            registry_summary="test",
        )
        # Check that the prompt passed to claude contained the PR instruction
        call_args = mock_run.call_args
        prompt_arg = call_args[0][0][2]  # The prompt is the 3rd arg in the command list
        assert "pull request" in prompt_arg.lower() or "gh pr create" in prompt_arg
