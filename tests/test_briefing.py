import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
from orchestrator.briefing import build_brief_prompt, generate_brief


class TestBuildBriefPrompt:
    def test_returns_string(self, tmp_path):
        prompt = build_brief_prompt(tmp_path)
        assert isinstance(prompt, str)

    def test_includes_cognitive_patterns(self, tmp_path):
        prompt = build_brief_prompt(tmp_path)
        assert "leverage" in prompt.lower()
        assert "inversion" in prompt.lower()

    def test_includes_no_data_defaults(self, tmp_path):
        prompt = build_brief_prompt(tmp_path)
        assert "no recent runs" in prompt.lower() or "no patterns" in prompt.lower()


class TestGenerateBrief:
    @patch("orchestrator.briefing.subprocess.run")
    def test_returns_output_on_success(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stdout="## Strategic Brief\nAll good.")
        result = generate_brief(tmp_path)
        assert "Strategic Brief" in result

    @patch("orchestrator.briefing.subprocess.run")
    def test_falls_back_on_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = generate_brief(tmp_path)
        assert isinstance(result, str)
        assert "Orchestrator Digest" in result  # fallback to simple digest

    @patch("orchestrator.briefing.subprocess.run")
    def test_falls_back_on_timeout(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        result = generate_brief(tmp_path)
        assert isinstance(result, str)
