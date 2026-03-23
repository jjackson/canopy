"""Tests for the canopy patterns CLI command."""
import json
from unittest.mock import patch
from click.testing import CliRunner
from orchestrator.cli import main


SAMPLE_PATTERNS = [
    {
        "type": "recurring_issue",
        "issue_type": "gap",
        "related_servers": ["connect-search"],
        "observation_count": 3,
        "total_frequency": 7,
        "unique_sessions": 5,
        "descriptions": ["Missing tool for X", "No way to Y"],
        "severity": "high",
        "actionable": True,
    },
    {
        "type": "project_hotspot",
        "server": "connect-search",
        "issue_count": 4,
        "high_severity_count": 2,
        "actionable": True,
    },
]


class TestPatternsCommand:
    def test_exit_code_zero(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=[]):
            result = runner.invoke(main, ["patterns"])
        assert result.exit_code == 0

    def test_no_patterns_message(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=[]):
            result = runner.invoke(main, ["patterns"])
        assert "No patterns" in result.output

    def test_shows_recurring_issues(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=SAMPLE_PATTERNS):
            result = runner.invoke(main, ["patterns"])
        assert "connect-search" in result.output
        assert "recurring" in result.output.lower() or "gap" in result.output.lower()

    def test_json_output(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=SAMPLE_PATTERNS):
            result = runner.invoke(main, ["patterns", "--json-output"])
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["type"] == "recurring_issue"

    def test_shows_hotspots(self):
        runner = CliRunner()
        with patch("orchestrator.patterns.detect_patterns", return_value=SAMPLE_PATTERNS):
            result = runner.invoke(main, ["patterns"])
        assert "hotspot" in result.output.lower() or "connect-search" in result.output
