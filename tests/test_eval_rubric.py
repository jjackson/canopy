"""The rubric scorer — ACE's verdict-schema math, ported generic: weighted
dimensions → overall score + tier. Pure; the LLM that produces the per-dimension
scores is a separate (untestable) seam."""
import pytest

from orchestrator.eval_rubric import score_rubric


def test_weighted_overall_and_dimensions_preserved():
    out = score_rubric([
        {"name": "design", "score": 90, "weight": 2},
        {"name": "correctness", "score": 60, "weight": 1},
    ])
    assert out["overall_score"] == 80.0          # (90*2 + 60*1)/3
    assert out["verdict"] == "pass"
    assert [d["name"] for d in out["dimensions"]] == ["design", "correctness"]


def test_weight_defaults_to_one():
    out = score_rubric([{"name": "a", "score": 80}, {"name": "b", "score": 60}])
    assert out["overall_score"] == 70.0


def test_tier_thresholds():
    assert score_rubric([{"name": "x", "score": 70}])["verdict"] == "pass"
    assert score_rubric([{"name": "x", "score": 50}])["verdict"] == "warn"
    assert score_rubric([{"name": "x", "score": 49}])["verdict"] == "fail"


def test_custom_thresholds():
    out = score_rubric([{"name": "x", "score": 85}], pass_at=90, warn_at=70)
    assert out["verdict"] == "warn"


def test_empty_dimensions_raises():
    with pytest.raises(ValueError, match="at least one"):
        score_rubric([])


def test_zero_total_weight_raises():
    with pytest.raises(ValueError, match="weight"):
        score_rubric([{"name": "x", "score": 80, "weight": 0}])
