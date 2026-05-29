"""Tests for scripts.ddd.narrative_coherence."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.ddd.narrative_coherence import (
    OUTCOME_PATTERNS,
    narrative_coherence,
)
from scripts.ddd.schemas.models import UnifiedSpec


def _minimal_spec(scenes: list[dict]) -> dict:
    """Build a minimal valid spec dict around the given scenes."""
    return {
        "name": "test-feature",
        "narrative": "Test narrative for the spec.",
        "base_url": "https://example.com",
        "personas": {
            "lead": {
                "name": "Dana",
                "role": "Lead",
                "color": "#000000",
                "intro": "Intro.",
            }
        },
        "scenes": scenes,
    }


def _scene(title: str, show: str, claim: str, persona: str = "lead", provenance: str = "p1") -> dict:
    return {
        "persona": persona,
        "title": title,
        "show": show,
        "concept_claim": claim,
        "provenance": provenance,
        "features": [
            {
                "id": "f1",
                "description": "A buildable thing.",
                "verify": "It is buildable.",
            }
        ],
    }


# ---------------------------------------------------------------------------
# Pass cases — legitimate input-config mentions must NOT be flagged.
# ---------------------------------------------------------------------------


def test_pass_clean_spec():
    spec = _minimal_spec([
        _scene(
            "Dana picks the config",
            "Dana picks GeoPoDe Nigeria, Coverage mode, Balanced, 100 buildings per work area, ±10% tolerance, and hits materialize.",
            "One config materializes plans against real Overture footprints, so the lead does not re-enter settings ten times.",
        ),
    ])
    v = narrative_coherence(spec)
    assert v.verdict == "pass", v.blocking_reason


def test_pass_input_config_numbers_not_flagged():
    """100 buildings per work area, opportunity 123, program 135 — all inputs, not outputs."""
    spec = _minimal_spec([
        _scene(
            "Beat",
            "Dana opens program 135 and picks opportunity 123 for Deploy.",
            "The lead binds the chosen opportunity to the plans on Deploy.",
        ),
        _scene(
            "Beat 2",
            "100 buildings per work area, balance tolerance ±10%, ten ward names entered into the config.",
            "One config materializes the batch; nothing entered is a system output.",
            provenance="p2",
        ),
    ])
    v = narrative_coherence(spec)
    assert v.verdict == "pass", v.blocking_reason


# ---------------------------------------------------------------------------
# Fail cases — each catches a real failure mode seen in the microplans spec.
# ---------------------------------------------------------------------------


def test_fail_work_area_count_in_setup_beat():
    """The materialize beat must not pre-commit to per-plan work-area counts."""
    spec = _minimal_spec([
        _scene(
            "Dana materializes ten plans",
            "Dana hits Materialize and watches Galinja's 7 work areas, Jibga's 43 work areas, Gora's 53 work areas land.",
            "One config materializes ten plans against real Overture footprints.",
        ),
    ])
    v = narrative_coherence(spec)
    assert v.verdict == "fail"
    assert "work-area count" in (v.blocking_reason or "")
    assert "Galinja's 7 work areas" not in (v.blocking_reason or "")  # the LABEL is in reason; the matched substring is "7 work areas"
    assert "7 work areas" in (v.blocking_reason or "") or "43 work areas" in (v.blocking_reason or "")


def test_fail_fit_score_leakage():
    """Fit scores are computed from the materialized plans — outputs, not inputs."""
    spec = _minimal_spec([
        _scene(
            "Dana compares the plans",
            "Dana opens compare and sees Galinja ★ 98.7 best, Jibga fit 20.0 worst.",
            "The comparison surfaces fit scores so the lead can spot outliers.",
        ),
    ])
    v = narrative_coherence(spec)
    assert v.verdict == "fail"
    reason = v.blocking_reason or ""
    assert ("fit score" in reason) or ("★" in reason)


def test_fail_imbalance_percentage_leakage():
    """Workload imbalance % is a KPI computed after assignment."""
    spec = _minimal_spec([
        _scene(
            "Dana flags the outlier",
            "Dana sees Jibga at 106% imbalance and Madobi at 100% imbalance and re-tunes.",
            "The tool surfaces the imbalance outlier so the lead can act on it.",
        ),
    ])
    v = narrative_coherence(spec)
    assert v.verdict == "fail"
    assert "imbalance" in (v.blocking_reason or "")


def test_fail_lifecycle_split_leakage():
    """The 8 Approved + 2 In review split is a consequence of LLO decisions."""
    spec = _minimal_spec([
        _scene(
            "Dana reviews the audit",
            "Dana sees the 8 Approved + 2 In review state in the audit panel.",
            "The lead reads the planning audit before sign-off.",
        ),
    ])
    v = narrative_coherence(spec)
    assert v.verdict == "fail"
    assert "lifecycle split" in (v.blocking_reason or "")


def test_fail_max_travel_km_leakage():
    """Max travel km is a KPI computed from work-area geometry."""
    spec = _minimal_spec([
        _scene(
            "Dana spots the long-travel ward",
            "Dana sees Jibga at 15.3 km max travel and Gora at 9.7 km max travel.",
            "The lead identifies the long-travel outliers.",
        ),
    ])
    v = narrative_coherence(spec)
    assert v.verdict == "fail"
    assert "travel" in (v.blocking_reason or "") or "spread" in (v.blocking_reason or "")


# ---------------------------------------------------------------------------
# CLI smoke / Verdict shape.
# ---------------------------------------------------------------------------


def test_returns_verdict_shape_on_missing_path(tmp_path: Path):
    missing = tmp_path / "no-such-spec.yaml"
    v = narrative_coherence(missing)
    assert v.verdict == "fail"
    assert "not found" in (v.blocking_reason or "")


def test_returns_verdict_shape_on_none():
    v = narrative_coherence(None)
    assert v.verdict == "fail"


def test_real_microplans_fixed_spec_passes():
    """The microplans-10-wards spec (after the coherence fix) should pass.

    Lives outside the canopy repo in the connect-labs worktree; skip if
    not present (CI environment, etc.).
    """
    spec_path = Path(
        "/Users/acedimagi/emdash/worktrees/connect-labs/emdash/product-management-xg1nb/docs/walkthroughs/microplans-10-wards.yaml"
    )
    if not spec_path.exists():
        pytest.skip("microplans-10-wards spec not present in this checkout")
    v = narrative_coherence(spec_path)
    assert v.verdict == "pass", v.blocking_reason


def test_ddd_spec_passes():
    """The DDD-on-DDD spec should be coherence-clean (per-scene fields)."""
    spec_path = Path(
        "/Users/acedimagi/emdash/worktrees/connect-labs/emdash/product-management-xg1nb/docs/walkthroughs/ddd.yaml"
    )
    if not spec_path.exists():
        pytest.skip("ddd spec not present in this checkout")
    v = narrative_coherence(spec_path)
    assert v.verdict == "pass", v.blocking_reason
