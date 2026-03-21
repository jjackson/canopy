import json
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from orchestrator.server import create_app, get_transcripts, save_label_data

FIXTURE = Path(__file__).parent / "fixtures" / "sample_transcript.jsonl"


@pytest.fixture
def app_dirs(tmp_path):
    """Set up directory structure for the server."""
    projects_dir = tmp_path / "projects" / "-test-project"
    projects_dir.mkdir(parents=True)
    shutil.copy(FIXTURE, projects_dir / "test-session-001.jsonl")

    state_dir = tmp_path / "orchestrator"
    state_dir.mkdir()

    return {
        "projects_dir": tmp_path / "projects",
        "state_dir": state_dir,
        "registry_path": Path(__file__).parent / "fixtures" / "sample_registry.yaml",
    }


class TestCreateApp:
    def test_returns_handler_class(self, app_dirs):
        handler = create_app(**app_dirs)
        assert handler is not None


class TestGetTranscripts:
    def test_returns_list(self, app_dirs):
        result = get_transcripts(app_dirs["projects_dir"], app_dirs["state_dir"])
        assert isinstance(result, list)

    def test_finds_fixture_transcript(self, app_dirs):
        result = get_transcripts(app_dirs["projects_dir"], app_dirs["state_dir"])
        assert len(result) >= 1

    def test_transcript_has_metadata(self, app_dirs):
        result = get_transcripts(app_dirs["projects_dir"], app_dirs["state_dir"])
        t = result[0]
        assert "session_id" in t
        assert "lines" in t
        assert "user_msgs" in t
        assert "first_msg" in t


class TestSaveLabels:
    def test_save_and_retrieve(self, app_dirs):
        save_label_data(app_dirs["state_dir"], "test-session-001", {
            "quality": "had-friction",
            "use_case_tags": ["test"],
            "eval_candidate": True,
            "notes": "test note",
        })
        transcripts = get_transcripts(app_dirs["projects_dir"], app_dirs["state_dir"])
        t = [t for t in transcripts if t["session_id"] == "test-session-001"][0]
        assert t["label"]["quality"] == "had-friction"
