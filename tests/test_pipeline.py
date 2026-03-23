from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from orchestrator.pipeline import run_cycle, CycleConfig


SCANNER_ENTRY = {
    "session_id": "s1",
    "path": str(Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"),
    "project_key": "-test-project",
    "lines": 100,
    "user_msgs": 10,
    "first_msg": "test",
    "first_ts": "2026-03-20T10:00:00",
    "last_ts": "2026-03-20T11:00:00",
    "mcp_servers": [],
    "mcp_call_count": 0,
    "repo": None,
    "label": {"quality": "unlabeled", "use_case_tags": [], "eval_candidate": False, "notes": ""},
}


class TestCycleConfig:
    def test_defaults(self):
        cfg = CycleConfig()
        assert cfg.max_transcripts == 10
        assert cfg.max_proposals == 3
        assert cfg.observe_only is False
        assert cfg.dry_run is False

    def test_observe_only(self):
        cfg = CycleConfig(observe_only=True)
        assert cfg.observe_only is True

    def test_dry_run(self):
        cfg = CycleConfig(dry_run=True)
        assert cfg.dry_run is True

    def test_max_failures(self):
        cfg = CycleConfig(max_failures=5)
        assert cfg.max_failures == 5

    def test_max_calls_per_hour(self):
        cfg = CycleConfig(max_calls_per_hour=20)
        assert cfg.max_calls_per_hour == 20


class TestRunCycleNoData:
    @patch("orchestrator.pipeline.scan_all_transcripts", return_value=[])
    def test_no_transcripts_returns_run_with_zero_counts(self, mock_scan, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()

        result = run_cycle(
            state_dir=state_dir,
            registry_path=Path(__file__).parent / "fixtures" / "sample_registry.yaml",
            config=CycleConfig(),
        )
        assert result["transcripts_analyzed"] == 0
        assert result["observations_created"] == 0
        assert result["proposals_generated"] == 0


class TestRunCycleObserveOnly:
    @patch("orchestrator.pipeline.analyze_transcript")
    @patch("orchestrator.pipeline.scan_all_transcripts")
    def test_observe_only_skips_proposals(self, mock_scan, mock_analyze, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()

        mock_scan.return_value = [SCANNER_ENTRY]
        mock_analyze.return_value = [{
            "type": "gap",
            "description": "test gap",
            "severity": "high",
            "related_servers": [],
            "lifecycle_stage": None,
            "evidence": "test",
        }]

        result = run_cycle(
            state_dir=state_dir,
            registry_path=Path(__file__).parent / "fixtures" / "sample_registry.yaml",
            config=CycleConfig(observe_only=True),
        )
        assert result["transcripts_analyzed"] == 1
        assert result["observations_created"] == 1
        assert result["proposals_generated"] == 0


class TestRunCycleDryRun:
    @patch("orchestrator.pipeline.generate_proposals")
    @patch("orchestrator.pipeline.analyze_transcript")
    @patch("orchestrator.pipeline.scan_all_transcripts")
    def test_dry_run_skips_implementation(self, mock_scan, mock_analyze, mock_propose, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()

        mock_scan.return_value = [SCANNER_ENTRY]
        mock_analyze.return_value = [{
            "type": "gap",
            "description": "test",
            "severity": "high",
            "related_servers": [],
            "lifecycle_stage": None,
            "evidence": "test",
        }]
        mock_propose.return_value = [{
            "type": "new_tool",
            "action": "Create tool",
            "target_repo": "~/repo",
            "ownership": "self",
            "motivation": "needed",
            "observation_id": "obs-1",
            "complexity": "low",
        }]

        result = run_cycle(
            state_dir=state_dir,
            registry_path=Path(__file__).parent / "fixtures" / "sample_registry.yaml",
            config=CycleConfig(dry_run=True),
        )
        assert result["proposals_generated"] == 1
        assert result["proposals_implemented"] == 0


class TestRunCycleCircuitBreaker:
    @patch("orchestrator.pipeline.analyze_transcript")
    @patch("orchestrator.pipeline.scan_all_transcripts")
    def test_stops_after_consecutive_failures(self, mock_scan, mock_analyze, tmp_path):
        state_dir = tmp_path / "orchestrator"
        state_dir.mkdir()

        mock_scan.return_value = [
            {**SCANNER_ENTRY, "session_id": f"s{i}"}
            for i in range(5)
        ]
        mock_analyze.side_effect = RuntimeError("API error")

        result = run_cycle(
            state_dir=state_dir,
            registry_path=Path(__file__).parent / "fixtures" / "sample_registry.yaml",
            config=CycleConfig(observe_only=True, max_failures=3),
        )
        assert result.get("circuit_breaker_tripped") is True
        assert len(result.get("errors", [])) > 0
