"""Tests for the canopy brief CLI command."""
from unittest.mock import patch
from click.testing import CliRunner
from orchestrator.cli import main


class TestBriefCommand:
    def test_exit_code_zero(self):
        runner = CliRunner()
        with patch("orchestrator.briefing.generate_brief", return_value="# Strategic Brief\n\nAll clear."):
            result = runner.invoke(main, ["brief"])
        assert result.exit_code == 0

    def test_outputs_brief_content(self):
        runner = CliRunner()
        brief_text = "# Strategic Brief\n\nPattern: recurring friction in connect-search."
        with patch("orchestrator.briefing.generate_brief", return_value=brief_text):
            result = runner.invoke(main, ["brief"])
        assert "recurring friction" in result.output

    def test_passes_model_option(self):
        runner = CliRunner()
        with patch("orchestrator.briefing.generate_brief", return_value="brief") as mock:
            runner.invoke(main, ["brief", "--model", "opus"])
        mock.assert_called_once()
        assert mock.call_args[1]["model"] == "opus"

    def test_passes_budget_option(self):
        runner = CliRunner()
        with patch("orchestrator.briefing.generate_brief", return_value="brief") as mock:
            runner.invoke(main, ["brief", "--budget", "2.0"])
        mock.assert_called_once()
        assert mock.call_args[1]["max_budget_usd"] == 2.0
