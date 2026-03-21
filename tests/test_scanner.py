import json
from pathlib import Path
import pytest
from orchestrator.scanner import scan_transcript, scan_all_transcripts


FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


class TestScanTranscript:
    def test_returns_dict(self):
        result = scan_transcript(FIXTURE)
        assert isinstance(result, dict)

    def test_has_session_id(self):
        result = scan_transcript(FIXTURE)
        assert result["session_id"] == "test-session-001"

    def test_has_file_path(self):
        result = scan_transcript(FIXTURE)
        assert result["path"] == str(FIXTURE)

    def test_has_line_count(self):
        result = scan_transcript(FIXTURE)
        assert result["lines"] > 0

    def test_has_user_message_count(self):
        result = scan_transcript(FIXTURE)
        assert result["user_msgs"] > 0

    def test_has_first_message(self):
        result = scan_transcript(FIXTURE)
        assert "maternal health" in result["first_msg"].lower()

    def test_has_mcp_tools(self):
        result = scan_transcript(FIXTURE)
        assert "connect_search" in result["mcp_servers"]

    def test_has_mcp_call_count(self):
        result = scan_transcript(FIXTURE)
        assert result["mcp_call_count"] >= 2

    def test_has_timestamps(self):
        result = scan_transcript(FIXTURE)
        assert result["first_ts"] is not None
        assert result["last_ts"] is not None

    def test_has_project_key(self):
        result = scan_transcript(FIXTURE)
        assert "project_key" in result


class TestScanAllTranscripts:
    def test_returns_list(self, tmp_path):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        result = scan_all_transcripts(projects_dir)
        assert isinstance(result, list)

    def test_finds_transcripts(self, tmp_path):
        projects_dir = tmp_path / "projects"
        proj = projects_dir / "-test-project"
        proj.mkdir(parents=True)
        # Copy fixture
        import shutil
        shutil.copy(FIXTURE, proj / "abc123.jsonl")
        result = scan_all_transcripts(projects_dir)
        assert len(result) == 1

    def test_skips_non_jsonl(self, tmp_path):
        projects_dir = tmp_path / "projects"
        proj = projects_dir / "-test-project"
        proj.mkdir(parents=True)
        (proj / "not-a-transcript.txt").write_text("hello")
        result = scan_all_transcripts(projects_dir)
        assert len(result) == 0

    def test_includes_repo_from_map(self, tmp_path):
        projects_dir = tmp_path / "projects"
        proj = projects_dir / "-test-project"
        proj.mkdir(parents=True)
        import shutil
        shutil.copy(FIXTURE, proj / "abc123.jsonl")
        repo_map = {"-test-project": "owner/my-repo"}
        result = scan_all_transcripts(projects_dir, repo_map=repo_map)
        assert result[0]["repo"] == "owner/my-repo"
