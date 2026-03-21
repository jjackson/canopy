from pathlib import Path
from unittest.mock import patch
from click.testing import CliRunner
from orchestrator.cli import main


class TestImproveCommand:
    @patch("orchestrator.cli.run_cycle")
    def test_improve_calls_run_cycle(self, mock_cycle):
        mock_cycle.return_value = {
            "transcripts_analyzed": 0,
            "observations_created": 0,
            "proposals_generated": 0,
            "proposals_implemented": 0,
        }
        runner = CliRunner()
        result = runner.invoke(main, ["improve"])
        assert result.exit_code == 0

    @patch("orchestrator.cli.run_cycle")
    def test_improve_observe_only(self, mock_cycle):
        mock_cycle.return_value = {
            "transcripts_analyzed": 2,
            "observations_created": 3,
            "proposals_generated": 0,
            "proposals_implemented": 0,
        }
        runner = CliRunner()
        result = runner.invoke(main, ["improve", "--observe-only"])
        assert result.exit_code == 0
        assert "observe-only" in result.output.lower()

    @patch("orchestrator.cli.run_cycle")
    def test_improve_dry_run(self, mock_cycle):
        mock_cycle.return_value = {
            "transcripts_analyzed": 1,
            "observations_created": 1,
            "proposals_generated": 2,
            "proposals_implemented": 0,
        }
        runner = CliRunner()
        result = runner.invoke(main, ["improve", "--dry-run"])
        assert result.exit_code == 0

    @patch("orchestrator.cli.run_cycle")
    def test_improve_shows_summary(self, mock_cycle):
        mock_cycle.return_value = {
            "transcripts_analyzed": 3,
            "observations_created": 2,
            "proposals_generated": 1,
            "proposals_implemented": 1,
        }
        runner = CliRunner()
        result = runner.invoke(main, ["improve"])
        assert "3" in result.output
