from pathlib import Path
from orchestrator.tracker import (
    record_outcome, load_outcomes, compute_success_rates, get_prioritization_weights,
)


class TestRecordAndLoad:
    def test_creates_file(self, tmp_path):
        path = tmp_path / "tracker.jsonl"
        record_outcome(path, "obs-1", "prop-1", "implemented")
        assert path.exists()

    def test_round_trip(self, tmp_path):
        path = tmp_path / "tracker.jsonl"
        record_outcome(path, "obs-1", "prop-1", "implemented", evidence="5 tests pass")
        outcomes = load_outcomes(path)
        assert len(outcomes) == 1
        assert outcomes[0]["outcome"] == "implemented"
        assert outcomes[0]["evidence"] == "5 tests pass"

    def test_multiple_records(self, tmp_path):
        path = tmp_path / "tracker.jsonl"
        record_outcome(path, "o1", "p1", "implemented")
        record_outcome(path, "o2", "p2", "failed")
        assert len(load_outcomes(path)) == 2

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_outcomes(tmp_path / "nope.jsonl") == []


class TestSuccessRates:
    def test_by_type(self):
        outcomes = [
            {"proposal_type": "new_tool", "outcome": "implemented", "verification_confidence": "high"},
            {"proposal_type": "new_tool", "outcome": "implemented", "verification_confidence": "high"},
            {"proposal_type": "new_tool", "outcome": "failed", "verification_confidence": "high"},
        ]
        rates = compute_success_rates(outcomes)
        assert abs(rates["by_type"]["new_tool"] - 0.667) < 0.01

    def test_by_confidence(self):
        outcomes = [
            {"proposal_type": "x", "outcome": "implemented", "verification_confidence": "high"},
            {"proposal_type": "x", "outcome": "failed", "verification_confidence": "low"},
        ]
        rates = compute_success_rates(outcomes)
        assert rates["by_confidence"]["high"] == 1.0
        assert rates["by_confidence"]["low"] == 0.0


class TestPrioritizationWeights:
    def test_high_confidence_gets_higher_weight(self):
        outcomes = [
            {"proposal_type": "x", "outcome": "implemented", "verification_confidence": "high"},
            {"proposal_type": "x", "outcome": "implemented", "verification_confidence": "high"},
            {"proposal_type": "x", "outcome": "failed", "verification_confidence": "low"},
            {"proposal_type": "x", "outcome": "failed", "verification_confidence": "low"},
        ]
        weights = get_prioritization_weights(outcomes)
        assert weights["high"] > weights["low"]

    def test_defaults_when_no_data(self):
        weights = get_prioritization_weights([])
        assert "high" in weights
        assert "low" in weights
