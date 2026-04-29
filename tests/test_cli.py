"""Tests for orchestrator.cli module."""

import json
from pathlib import Path
from unittest import mock

import pytest
from click.testing import CliRunner

from orchestrator.cli import main

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_REGISTRY = FIXTURES_DIR / "sample_registry.yaml"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _runner_with_registry(registry_path: Path = SAMPLE_REGISTRY):
    """Return a CliRunner and a monkeypatched find_registry callable."""
    runner = CliRunner()
    return runner


def _invoke(args, registry_path: Path = SAMPLE_REGISTRY, env: dict | None = None):
    """Invoke the CLI with find_registry monkeypatched to use the test fixture."""
    runner = CliRunner(env=env)
    with mock.patch("orchestrator.cli.find_registry", return_value=registry_path):
        result = runner.invoke(main, args)
    return result


# ---------------------------------------------------------------------------
# orchestrator registry show (summary, default)
# ---------------------------------------------------------------------------


class TestRegistryShow:
    def test_exit_code_zero(self):
        result = _invoke(["registry", "show"])
        assert result.exit_code == 0

    def test_shows_server_count(self):
        result = _invoke(["registry", "show"])
        assert "2 servers" in result.output

    def test_shows_server_names(self):
        result = _invoke(["registry", "show"])
        assert "commcare-hq" in result.output
        assert "solicitations" in result.output

    def test_shows_version(self):
        result = _invoke(["registry", "show"])
        assert "Registry v1" in result.output

    def test_shows_tool_count(self):
        result = _invoke(["registry", "show"])
        # Each server has 2 tools listed
        assert "2 tools" in result.output


# ---------------------------------------------------------------------------
# orchestrator registry show --format skill
# ---------------------------------------------------------------------------


class TestRegistryShowSkillFormat:
    def test_exit_code_zero(self):
        result = _invoke(["registry", "show", "--format", "skill"])
        assert result.exit_code == 0

    def test_outputs_markdown_heading(self):
        result = _invoke(["registry", "show", "--format", "skill"])
        assert "# Capability Registry" in result.output

    def test_contains_domain(self):
        result = _invoke(["registry", "show", "--format", "skill"])
        assert "connect" in result.output

    def test_contains_server_names(self):
        result = _invoke(["registry", "show", "--format", "skill"])
        assert "commcare-hq" in result.output
        assert "solicitations" in result.output


# ---------------------------------------------------------------------------
# orchestrator registry show --format json
# ---------------------------------------------------------------------------


class TestRegistryShowJsonFormat:
    def test_exit_code_zero(self):
        result = _invoke(["registry", "show", "--format", "json"])
        assert result.exit_code == 0

    def test_output_is_valid_json(self):
        result = _invoke(["registry", "show", "--format", "json"])
        parsed = json.loads(result.output)
        assert isinstance(parsed, dict)

    def test_json_contains_version(self):
        result = _invoke(["registry", "show", "--format", "json"])
        parsed = json.loads(result.output)
        assert parsed["version"] == 1

    def test_json_contains_domains(self):
        result = _invoke(["registry", "show", "--format", "json"])
        parsed = json.loads(result.output)
        assert "domains" in parsed
        assert "connect" in parsed["domains"]


# ---------------------------------------------------------------------------
# orchestrator registry validate
# ---------------------------------------------------------------------------


class TestRegistryValidate:
    def test_exit_code_zero_for_valid_registry(self):
        result = _invoke(["registry", "validate"])
        assert result.exit_code == 0

    def test_outputs_registry_is_valid(self):
        result = _invoke(["registry", "validate"])
        assert "Registry is valid." in result.output

    def test_invalid_registry_reports_errors(self, tmp_path):
        """A registry with a server missing tools should report errors."""
        import yaml
        bad_registry = tmp_path / "bad_registry.yaml"
        data = {
            "version": 1,
            "domains": {
                "test": {
                    "servers": {
                        "my-server": {
                            "description": "A server with no tools",
                            # tools, answers, and ownership are missing
                        }
                    }
                }
            },
        }
        bad_registry.write_text(yaml.dump(data))
        result = _invoke(["registry", "validate"], registry_path=bad_registry)
        assert result.exit_code != 0

    def test_validate_missing_registry_fails(self):
        """When find_registry raises ClickException, CLI exits non-zero."""
        runner = CliRunner()
        # Run without monkeypatching; relies on no registry.yaml in cwd during test
        with mock.patch("orchestrator.cli.find_registry", side_effect=Exception("not found")):
            result = runner.invoke(main, ["registry", "validate"])
        # ClickException produces exit_code 1; a raw Exception exits 1 as well
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# orchestrator sessions status
# ---------------------------------------------------------------------------


class TestSessionsStatus:
    def test_no_log_file_outputs_not_found(self, tmp_path):
        """When the log file does not exist, output says no entries found."""
        nonexistent = tmp_path / "session-log.jsonl"
        runner = CliRunner()
        with mock.patch("orchestrator.cli.Path") as mock_path_cls:
            # We need to intercept the specific Path used inside sessions_status.
            # Easier: patch read_session_log to return [].
            with mock.patch("orchestrator.cli.read_session_log", return_value=[]):
                result = runner.invoke(main, ["sessions", "status"])
        assert result.exit_code == 0
        assert "No session log entries found." in result.output

    def test_no_log_file_exit_code_zero(self, tmp_path):
        runner = CliRunner()
        with mock.patch("orchestrator.cli.read_session_log", return_value=[]):
            result = runner.invoke(main, ["sessions", "status"])
        assert result.exit_code == 0

    def test_with_entries_shows_count(self):
        entries = [
            {"session_id": "s1", "server": "commcare-hq", "tool": "get_app_structure",
             "ts": "2026-03-20T10:00:00+00:00"},
            {"session_id": "s1", "server": "solicitations", "tool": "create_solicitation",
             "ts": "2026-03-20T10:01:00+00:00"},
            {"session_id": "s2", "server": "commcare-hq", "tool": "get_form_questions",
             "ts": "2026-03-20T10:02:00+00:00"},
        ]
        runner = CliRunner()
        with mock.patch("orchestrator.cli.read_session_log", return_value=entries):
            result = runner.invoke(main, ["sessions", "status"])
        assert result.exit_code == 0
        assert "3 entries" in result.output

    def test_with_entries_shows_session_count(self):
        entries = [
            {"session_id": "s1", "server": "commcare-hq", "tool": "t1",
             "ts": "2026-03-20T10:00:00+00:00"},
            {"session_id": "s2", "server": "solicitations", "tool": "t2",
             "ts": "2026-03-20T10:01:00+00:00"},
        ]
        runner = CliRunner()
        with mock.patch("orchestrator.cli.read_session_log", return_value=entries):
            result = runner.invoke(main, ["sessions", "status"])
        assert "2 sessions" in result.output

    def test_with_entries_shows_latest(self):
        entries = [
            {"session_id": "s1", "server": "commcare-hq", "tool": "first_tool",
             "ts": "2026-03-20T10:00:00+00:00"},
            {"session_id": "s1", "server": "solicitations", "tool": "last_tool",
             "ts": "2026-03-20T10:01:00+00:00"},
        ]
        runner = CliRunner()
        with mock.patch("orchestrator.cli.read_session_log", return_value=entries):
            result = runner.invoke(main, ["sessions", "status"])
        assert "solicitations.last_tool" in result.output


# ---------------------------------------------------------------------------
# canopy skills find
# ---------------------------------------------------------------------------


class TestSkillsFind:
    """Tests for `canopy skills find <query>`."""

    SAMPLE_CATALOG = [
        {
            "name": "test-audit",
            "qualified": "canopy:test-audit",
            "scope": "plugin",
            "source": "canopy",
            "kind": "skill",
            "description": "Audit a Python pytest test suite and prune dumb tests",
            "path": "/abs/canopy/skills/test-audit/SKILL.md",
        },
        {
            "name": "doctor",
            "qualified": "canopy:doctor",
            "scope": "plugin",
            "source": "canopy",
            "kind": "skill",
            "description": "Diagnose canopy plugin health",
            "path": "/abs/canopy/skills/doctor/SKILL.md",
        },
        {
            "name": "improve",
            "qualified": "canopy:improve",
            "scope": "plugin",
            "source": "canopy",
            "kind": "skill",
            "description": "Run a full canopy improvement cycle from session analysis",
            "path": "/abs/canopy/skills/improve/SKILL.md",
        },
    ]

    def test_audit_tests_returns_test_audit_first(self):
        runner = CliRunner()
        with mock.patch(
            "orchestrator.skill_catalog.build_catalog",
            return_value=list(self.SAMPLE_CATALOG),
        ):
            result = runner.invoke(main, ["skills", "find", "audit", "tests"])
        assert result.exit_code == 0, result.output
        assert "canopy:test-audit" in result.output
        # First match line should be test-audit (rank highest)
        first_match = [
            line for line in result.output.splitlines() if "canopy:" in line
        ][0]
        assert "canopy:test-audit" in first_match

    def test_no_matches_message(self):
        runner = CliRunner()
        with mock.patch(
            "orchestrator.skill_catalog.build_catalog",
            return_value=list(self.SAMPLE_CATALOG),
        ):
            result = runner.invoke(main, ["skills", "find", "zzznevermatchesxxx"])
        assert result.exit_code == 0
        assert "No skills match" in result.output

    def test_json_output(self):
        runner = CliRunner()
        with mock.patch(
            "orchestrator.skill_catalog.build_catalog",
            return_value=list(self.SAMPLE_CATALOG),
        ):
            result = runner.invoke(
                main, ["skills", "find", "audit", "--json-output"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert any(e["qualified"] == "canopy:test-audit" for e in data)

    def test_limit_respected(self):
        runner = CliRunner()
        with mock.patch(
            "orchestrator.skill_catalog.build_catalog",
            return_value=list(self.SAMPLE_CATALOG),
        ):
            # query 'canopy' matches all three by description
            result = runner.invoke(
                main, ["skills", "find", "canopy", "--limit", "1", "--json-output"]
            )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1


# ---------------------------------------------------------------------------
# Top-level group help
# ---------------------------------------------------------------------------


class TestCliHelp:
    def test_main_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    def test_registry_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(main, ["registry", "--help"])
        assert result.exit_code == 0

    def test_sessions_help_exits_zero(self):
        runner = CliRunner()
        result = runner.invoke(main, ["sessions", "--help"])
        assert result.exit_code == 0
