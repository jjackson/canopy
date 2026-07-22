import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import yaml
import pytest
from orchestrator.analyzer import (
    build_analysis_prompt,
    parse_analysis_output,
    analyze_transcript,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


class TestBuildAnalysisPrompt:
    def test_returns_string(self):
        prompt = build_analysis_prompt(FIXTURE)
        assert isinstance(prompt, str)

    def test_includes_transcript_content(self):
        prompt = build_analysis_prompt(FIXTURE)
        assert "maternal health" in prompt.lower() or "search" in prompt.lower()


class TestParseAnalysisOutput:
    def test_parses_valid_yaml_list(self):
        output = yaml.dump([{
            "type": "gap",
            "description": "No training tool",
            "severity": "high",
            "related_servers": ["commcare-hq"],
            "lifecycle_stage": "training",
            "evidence": "user wrote manual manually",
        }])
        result = parse_analysis_output(output)
        assert len(result) == 1
        assert result[0]["type"] == "gap"

    def test_empty_list(self):
        assert parse_analysis_output("[]") == []

    def test_handles_yaml_with_markdown_fence(self):
        output = "```yaml\n- type: gap\n  description: test\n```"
        result = parse_analysis_output(output)
        assert len(result) == 1

    def test_handles_invalid_output(self):
        result = parse_analysis_output("This is not YAML at all!!!")
        assert result == []

    def test_rejects_non_list(self):
        result = parse_analysis_output("type: gap\ndescription: test")
        assert result == []


class TestAnalyzeTranscript:
    @patch("orchestrator.analyzer.subprocess.run")
    def test_returns_parsed_observations(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="- type: gap\n  description: test\n  severity: high\n  related_servers: []\n  lifecycle_stage: null\n  evidence: test",
        )
        result = analyze_transcript(FIXTURE)
        assert len(result) == 1
        assert result[0]["type"] == "gap"

    @patch("orchestrator.analyzer.subprocess.run")
    def test_returns_empty_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = analyze_transcript(FIXTURE)
        assert result == []

    @patch("orchestrator.analyzer.subprocess.run")
    def test_returns_empty_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        result = analyze_transcript(FIXTURE)
        assert result == []
