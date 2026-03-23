from pathlib import Path
import pytest
from orchestrator.observations import create_observation, save_observation
from orchestrator.patterns import detect_patterns, find_recurring_issues, find_project_hotspots


class TestFindRecurringIssues:
    def test_groups_by_type_and_servers(self):
        obs = [
            create_observation("gap", "Missing tool A", "high", "s1", related_servers=["server-x"]),
            create_observation("gap", "Missing tool B", "high", "s2", related_servers=["server-x"]),
        ]
        patterns = find_recurring_issues(obs)
        assert len(patterns) == 1
        assert patterns[0]["issue_type"] == "gap"

    def test_ignores_singletons(self):
        obs = [create_observation("gap", "Only one", "low", "s1")]
        assert find_recurring_issues(obs) == []

    def test_ranks_by_frequency(self):
        obs = [
            create_observation("gap", "A", "low", "s1", related_servers=["x"]),
            create_observation("gap", "B", "low", "s2", related_servers=["x"]),
            create_observation("friction", "C", "low", "s3", related_servers=["y"]),
            create_observation("friction", "D", "low", "s4", related_servers=["y"]),
            create_observation("friction", "E", "low", "s5", related_servers=["y"]),
        ]
        patterns = find_recurring_issues(obs)
        assert patterns[0]["issue_type"] == "friction"

    def test_severity_is_max(self):
        obs = [
            create_observation("gap", "A", "low", "s1"),
            create_observation("gap", "B", "high", "s2"),
        ]
        patterns = find_recurring_issues(obs)
        assert patterns[0]["severity"] == "high"


class TestFindProjectHotspots:
    def test_counts_per_server(self):
        obs = [
            create_observation("gap", "A", "high", "s1", related_servers=["server-x"]),
            create_observation("friction", "B", "low", "s2", related_servers=["server-x"]),
            create_observation("gap", "C", "low", "s3", related_servers=["server-y"]),
        ]
        patterns = find_project_hotspots(obs)
        assert len(patterns) == 1  # only server-x has 2+
        assert patterns[0]["server"] == "server-x"
        assert patterns[0]["issue_count"] == 2

    def test_tracks_high_severity(self):
        obs = [
            create_observation("gap", "A", "high", "s1", related_servers=["x"]),
            create_observation("gap", "B", "high", "s2", related_servers=["x"]),
        ]
        patterns = find_project_hotspots(obs)
        assert patterns[0]["high_severity_count"] == 2
        assert patterns[0]["actionable"] is True


class TestDetectPatterns:
    def test_empty_returns_empty(self, tmp_path):
        assert detect_patterns(tmp_path) == []

    def test_finds_patterns_from_saved_observations(self, tmp_path):
        save_observation(create_observation("gap", "A", "high", "s1", related_servers=["x"]), tmp_path)
        save_observation(create_observation("gap", "B", "high", "s2", related_servers=["x"]), tmp_path)
        patterns = detect_patterns(tmp_path)
        assert len(patterns) >= 1
