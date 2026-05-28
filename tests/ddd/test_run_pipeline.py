"""Tests for scripts/ddd/run_pipeline.py (SP4.1 + SP4.2, TDD).

SP4.1 — assemble_run_state:
    given a RunState + two stub Verdicts + a findings list, the result has:
    - verdicts == {"concept": concept_path, "user_artifact": user_path}
    - findings == the provided list
    - phase == "judged"

SP4.2 — compute_convergence:
    - both verdicts overall_score >= 4.0 AND neither blocked → True
    - one verdict overall_score < 4.0 → False
    - both overall_score >= 4.0 but one verdict=="blocked" → False
    - both overall_score >= 4.5 → True

    Also: MAX_ITERATIONS constant exported at module level.
"""
from __future__ import annotations

import pytest

from scripts.ddd.schemas.models import Dimension, RunState, Verdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stub_verdict(
    overall_score: float,
    verdict_str: str = "pass",
) -> Verdict:
    """Create a minimal Verdict for testing."""
    return Verdict(
        schema_version=1,
        dimensions={
            "concept_clarity": Dimension(score=overall_score, weight=1.0),
        },
        overall_score=overall_score,
        verdict=verdict_str,  # type: ignore[arg-type]
        blocking_reason=None,
        fix_recommendation=None,
    )


def _stub_state(feature: str = "test-feature") -> RunState:
    return RunState(run_id=f"{feature}-2026-01-01-001", feature=feature)


# ---------------------------------------------------------------------------
# SP4.1 — assemble_run_state
# ---------------------------------------------------------------------------


class TestAssembleRunState:
    def test_sets_verdict_paths(self) -> None:
        from scripts.ddd.run_pipeline import assemble_run_state

        state = _stub_state()
        concept_v = _stub_verdict(4.5)
        user_v = _stub_verdict(4.0)

        result = assemble_run_state(
            state,
            concept_v,
            user_v,
            findings=[],
            concept_path="verdict-concept.yaml",
            user_path="verdict-user.yaml",
        )

        assert result.verdicts == {
            "concept": "verdict-concept.yaml",
            "user_artifact": "verdict-user.yaml",
        }

    def test_sets_findings(self) -> None:
        from scripts.ddd.run_pipeline import assemble_run_state

        state = _stub_state()
        findings = [
            {"scene": "Scene 1", "dimension": "design_soundness", "severity": "high"},
            {"scene": "Scene 2", "dimension": "concept_clarity", "severity": "low"},
        ]

        result = assemble_run_state(
            state,
            _stub_verdict(4.0),
            _stub_verdict(4.0),
            findings=findings,
        )

        assert result.findings == findings

    def test_sets_phase_to_judged(self) -> None:
        from scripts.ddd.run_pipeline import assemble_run_state

        state = _stub_state()

        result = assemble_run_state(
            state,
            _stub_verdict(4.0),
            _stub_verdict(4.0),
            findings=[],
        )

        assert result.phase == "judged"

    def test_default_paths_used_when_not_specified(self) -> None:
        from scripts.ddd.run_pipeline import assemble_run_state

        state = _stub_state()

        result = assemble_run_state(
            state,
            _stub_verdict(4.0),
            _stub_verdict(4.0),
            findings=[],
        )

        # Default paths
        assert result.verdicts["concept"] == "verdict-concept.yaml"
        assert result.verdicts["user_artifact"] == "verdict-user.yaml"

    def test_returns_runstate(self) -> None:
        from scripts.ddd.run_pipeline import assemble_run_state

        state = _stub_state()
        result = assemble_run_state(
            state,
            _stub_verdict(5.0),
            _stub_verdict(5.0),
            findings=[],
        )
        assert isinstance(result, RunState)

    def test_preserves_run_id_and_feature(self) -> None:
        from scripts.ddd.run_pipeline import assemble_run_state

        state = _stub_state("my-feature")
        result = assemble_run_state(
            state,
            _stub_verdict(4.0),
            _stub_verdict(4.0),
            findings=[],
        )
        assert result.run_id == state.run_id
        assert result.feature == "my-feature"

    def test_custom_paths(self) -> None:
        from scripts.ddd.run_pipeline import assemble_run_state

        state = _stub_state()
        result = assemble_run_state(
            state,
            _stub_verdict(4.0),
            _stub_verdict(4.0),
            findings=[],
            concept_path="runs/abc/verdict-concept.yaml",
            user_path="runs/abc/verdict-user.yaml",
        )
        assert result.verdicts["concept"] == "runs/abc/verdict-concept.yaml"
        assert result.verdicts["user_artifact"] == "runs/abc/verdict-user.yaml"


# ---------------------------------------------------------------------------
# SP4.2 — compute_convergence
# ---------------------------------------------------------------------------


class TestComputeConvergence:
    def test_both_at_threshold_returns_true(self) -> None:
        from scripts.ddd.run_pipeline import compute_convergence

        assert compute_convergence(_stub_verdict(4.0), _stub_verdict(4.0)) is True

    def test_one_below_threshold_returns_false(self) -> None:
        from scripts.ddd.run_pipeline import compute_convergence

        assert compute_convergence(_stub_verdict(3.9), _stub_verdict(4.0)) is False
        assert compute_convergence(_stub_verdict(4.0), _stub_verdict(3.9)) is False

    def test_both_above_threshold_but_one_blocked_returns_false(self) -> None:
        from scripts.ddd.run_pipeline import compute_convergence

        blocked = _stub_verdict(4.5, verdict_str="blocked")
        passing = _stub_verdict(4.5, verdict_str="pass")

        assert compute_convergence(blocked, passing) is False
        assert compute_convergence(passing, blocked) is False

    def test_both_above_threshold_pass(self) -> None:
        from scripts.ddd.run_pipeline import compute_convergence

        assert compute_convergence(_stub_verdict(4.5), _stub_verdict(5.0)) is True

    def test_both_exactly_4_default_threshold(self) -> None:
        from scripts.ddd.run_pipeline import compute_convergence

        assert compute_convergence(_stub_verdict(4.0), _stub_verdict(4.0)) is True

    def test_custom_threshold(self) -> None:
        from scripts.ddd.run_pipeline import compute_convergence

        # With threshold=3.0, a score of 3.5 should pass
        assert compute_convergence(_stub_verdict(3.5), _stub_verdict(3.5), threshold=3.0) is True
        # But 2.9 should not
        assert compute_convergence(_stub_verdict(2.9), _stub_verdict(3.5), threshold=3.0) is False

    def test_both_warn_with_score_3(self) -> None:
        """warn verdict at score 3 is below the default threshold of 4.0."""
        from scripts.ddd.run_pipeline import compute_convergence

        warn_v = _stub_verdict(3.0, verdict_str="warn")
        assert compute_convergence(warn_v, warn_v) is False

    def test_both_blocked_returns_false(self) -> None:
        from scripts.ddd.run_pipeline import compute_convergence

        blocked = _stub_verdict(5.0, verdict_str="blocked")
        assert compute_convergence(blocked, blocked) is False


# ---------------------------------------------------------------------------
# SP4.2 — MAX_ITERATIONS constant
# ---------------------------------------------------------------------------


class TestMaxIterations:
    def test_max_iterations_exists_and_is_3(self) -> None:
        from scripts.ddd.run_pipeline import MAX_ITERATIONS

        assert MAX_ITERATIONS == 3

    def test_max_iterations_is_int(self) -> None:
        from scripts.ddd.run_pipeline import MAX_ITERATIONS

        assert isinstance(MAX_ITERATIONS, int)
