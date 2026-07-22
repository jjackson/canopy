import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from orchestrator.reviewer import (
    build_review_prompt,
    run_review,
    save_review,
    load_review,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


class TestBuildReviewPrompt:
    def test_returns_string(self):
        prompt = build_review_prompt(FIXTURE)
        assert isinstance(prompt, str)

    def test_includes_strategic_questions(self):
        prompt = build_review_prompt(FIXTURE)
        assert "highest-leverage" in prompt.lower()


class TestRunReview:
    @patch("orchestrator.reviewer.subprocess.run")
    def test_returns_string_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="## Analysis\nGreat session.")
        result = run_review(FIXTURE)
        assert "Great session" in result

    @patch("orchestrator.reviewer.subprocess.run")
    def test_returns_none_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = run_review(FIXTURE)
        assert result is None

    @patch("orchestrator.reviewer.subprocess.run")
    def test_returns_none_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=120)
        result = run_review(FIXTURE)
        assert result is None


class TestSaveLoadReview:
    def test_round_trip(self, tmp_path):
        save_review(tmp_path, "session-1", "## Analysis\nGreat session.")
        loaded = load_review(tmp_path, "session-1")
        assert "Great session" in loaded

    def test_load_missing_returns_none(self, tmp_path):
        assert load_review(tmp_path, "nonexistent") is None
