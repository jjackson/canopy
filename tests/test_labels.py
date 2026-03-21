from pathlib import Path
import pytest
from orchestrator.labels import load_labels, save_label, get_label, QUALITY_VALUES


class TestQualityValues:
    def test_contains_expected_values(self):
        assert "unlabeled" in QUALITY_VALUES
        assert "went-well" in QUALITY_VALUES
        assert "had-friction" in QUALITY_VALUES
        assert "skip-coding" in QUALITY_VALUES
        assert "good-for-eval" in QUALITY_VALUES


class TestLoadLabels:
    def test_missing_file_returns_empty(self, tmp_path):
        assert load_labels(tmp_path / "labels.yaml") == {}

    def test_returns_dict(self, tmp_path):
        assert isinstance(load_labels(tmp_path / "labels.yaml"), dict)


class TestSaveAndGetLabel:
    def test_save_creates_file(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", quality="went-well")
        assert path.exists()

    def test_round_trip_quality(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", quality="had-friction")
        label = get_label(load_labels(path), "session-1")
        assert label["quality"] == "had-friction"

    def test_round_trip_tags(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", use_case_tags=["salesforce", "research"])
        label = get_label(load_labels(path), "session-1")
        assert "salesforce" in label["use_case_tags"]

    def test_round_trip_notes(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", notes="Good test case")
        label = get_label(load_labels(path), "session-1")
        assert label["notes"] == "Good test case"

    def test_round_trip_eval_candidate(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "session-1", eval_candidate=True)
        label = get_label(load_labels(path), "session-1")
        assert label["eval_candidate"] is True

    def test_get_unlabeled_returns_defaults(self, tmp_path):
        path = tmp_path / "labels.yaml"
        label = get_label(load_labels(path), "nonexistent")
        assert label["quality"] == "unlabeled"
        assert label["use_case_tags"] == []
        assert label["notes"] == ""
        assert label["eval_candidate"] is False

    def test_update_preserves_other_fields(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "s1", quality="went-well", notes="first note")
        save_label(path, "s1", quality="had-friction")
        label = get_label(load_labels(path), "s1")
        assert label["quality"] == "had-friction"
        assert label["notes"] == "first note"

    def test_multiple_sessions(self, tmp_path):
        path = tmp_path / "labels.yaml"
        save_label(path, "s1", quality="went-well")
        save_label(path, "s2", quality="disaster")
        labels = load_labels(path)
        assert get_label(labels, "s1")["quality"] == "went-well"
        assert get_label(labels, "s2")["quality"] == "disaster"
