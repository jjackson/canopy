from pathlib import Path
import pytest
from orchestrator.observations import (
    create_observation, save_observation, load_observation,
    list_observations, find_matching_observation, merge_observation,
)

class TestCreateObservation:
    def test_returns_dict(self):
        obs = create_observation(obs_type="gap", description="No tool for generating training materials", severity="high", session_id="abc123")
        assert isinstance(obs, dict)

    def test_has_required_fields(self):
        obs = create_observation(obs_type="gap", description="No tool for generating training materials", severity="high", session_id="abc123")
        assert obs["type"] == "gap"
        assert obs["description"] == "No tool for generating training materials"
        assert obs["severity"] == "high"
        assert obs["frequency"] == 1
        assert obs["sessions"] == ["abc123"]

    def test_optional_fields(self):
        obs = create_observation(obs_type="friction", description="search_documents returns too many results", severity="medium", session_id="def456", related_servers=["connect-search"], lifecycle_stage="research")
        assert obs["related_servers"] == ["connect-search"]
        assert obs["lifecycle_stage"] == "research"

    def test_has_id(self):
        obs = create_observation(obs_type="gap", description="test", severity="low", session_id="abc")
        assert "id" in obs
        assert isinstance(obs["id"], str)

    def test_has_created_date(self):
        obs = create_observation(obs_type="gap", description="test", severity="low", session_id="abc")
        assert "created" in obs

class TestSaveLoadRoundTrip:
    def test_save_creates_file(self, tmp_path):
        obs = create_observation("gap", "test", "low", "abc")
        path = save_observation(obs, tmp_path)
        assert path.exists()

    def test_save_returns_path(self, tmp_path):
        obs = create_observation("gap", "test", "low", "abc")
        path = save_observation(obs, tmp_path)
        assert isinstance(path, Path)

    def test_round_trip_preserves_fields(self, tmp_path):
        obs = create_observation("gap", "test desc", "high", "s1", related_servers=["server-a"])
        path = save_observation(obs, tmp_path)
        loaded = load_observation(path)
        assert loaded["type"] == "gap"
        assert loaded["description"] == "test desc"
        assert loaded["severity"] == "high"
        assert loaded["related_servers"] == ["server-a"]

    def test_filename_uses_id(self, tmp_path):
        obs = create_observation("gap", "test", "low", "abc")
        path = save_observation(obs, tmp_path)
        assert obs["id"] in path.name

class TestListObservations:
    def test_returns_list(self, tmp_path):
        assert isinstance(list_observations(tmp_path), list)

    def test_empty_dir_returns_empty(self, tmp_path):
        assert list_observations(tmp_path) == []

    def test_finds_saved_observations(self, tmp_path):
        save_observation(create_observation("gap", "test1", "low", "s1"), tmp_path)
        save_observation(create_observation("friction", "test2", "high", "s2"), tmp_path)
        assert len(list_observations(tmp_path)) == 2

    def test_filter_by_type(self, tmp_path):
        save_observation(create_observation("gap", "t1", "low", "s1"), tmp_path)
        save_observation(create_observation("friction", "t2", "high", "s2"), tmp_path)
        assert len(list_observations(tmp_path, obs_type="gap")) == 1

    def test_filter_by_status(self, tmp_path):
        save_observation(create_observation("gap", "t1", "low", "s1"), tmp_path)
        assert len(list_observations(tmp_path, status="pending")) == 1
        assert len(list_observations(tmp_path, status="addressed")) == 0

class TestFindMatchingObservation:
    def test_finds_match_by_type_and_servers(self):
        existing = [create_observation("gap", "test", "low", "s1", related_servers=["server-a"], lifecycle_stage="research")]
        new = create_observation("gap", "different desc", "high", "s2", related_servers=["server-a"], lifecycle_stage="research")
        assert find_matching_observation(new, existing) is not None

    def test_no_match_different_type(self):
        existing = [create_observation("gap", "test", "low", "s1")]
        new = create_observation("friction", "test", "low", "s2")
        assert find_matching_observation(new, existing) is None

    def test_no_match_different_servers(self):
        existing = [create_observation("gap", "test", "low", "s1", related_servers=["server-a"])]
        new = create_observation("gap", "test", "low", "s2", related_servers=["server-b"])
        assert find_matching_observation(new, existing) is None

    def test_skips_addressed_observations(self):
        existing = [create_observation("gap", "test", "low", "s1")]
        existing[0]["status"] = "addressed"
        new = create_observation("gap", "test", "low", "s2")
        assert find_matching_observation(new, existing) is None

class TestMergeObservation:
    def test_increments_frequency(self):
        existing = create_observation("gap", "test", "low", "s1")
        merged = merge_observation(existing, session_id="s2")
        assert merged["frequency"] == 2

    def test_appends_session(self):
        existing = create_observation("gap", "test", "low", "s1")
        merged = merge_observation(existing, session_id="s2")
        assert "s2" in merged["sessions"]

    def test_preserves_original_fields(self):
        existing = create_observation("gap", "test", "high", "s1", related_servers=["server-a"])
        merged = merge_observation(existing, session_id="s2")
        assert merged["type"] == "gap"
        assert merged["related_servers"] == ["server-a"]

    def test_escalates_severity_if_frequent(self):
        existing = create_observation("gap", "test", "low", "s1")
        existing["frequency"] = 4
        existing["sessions"] = ["s1", "s2", "s3", "s4"]
        merged = merge_observation(existing, session_id="s5")
        assert merged["severity"] == "high"
