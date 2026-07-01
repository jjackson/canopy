"""Tests for scripts/ddd/verdicts.py — the unified verdict loader (canopy#265 item 1).

Six verdict artifacts, three historical structural schemas:
  * concept/user/actionability/why — the canonical weighted-dimension Verdict YAML
  * verdict-timing.json — render_locally.py's deterministic shape
    ({verdict, overallScore, coverage, findings[]}, camelCase, no dimensions)
  * verdict-video.json — the video judge's per-scene shape
    ({scenes:[{beat, scores{}, overall, verdict, findings[]}], ...})

load_verdict() normalizes any of them into the one Verdict model, stamping
kind / gate / live_state_verified defaults per verdict family so the aggregator
and convergence can be generic over N verdicts.
"""
from __future__ import annotations

import json

import pytest
import yaml

from scripts.ddd.schemas.models import Verdict
from scripts.ddd.verdicts import KIND_DEFAULTS, load_verdict


# ---------------------------------------------------------------------------
# Canonical YAML verdicts
# ---------------------------------------------------------------------------


def _write_concept_yaml(path, overall=4.5):
    path.write_text(
        yaml.dump(
            {
                "schema_version": 1,
                "dimensions": {"concept_clarity": {"score": overall, "weight": 1.0}},
                "overall_score": overall,
                "verdict": "pass",
            }
        )
    )


def test_yaml_verdict_loads_with_kind_defaults(tmp_path):
    p = tmp_path / "verdict-concept.yaml"
    _write_concept_yaml(p)
    v = load_verdict(p)
    assert isinstance(v, Verdict)
    assert v.kind == "concept"
    assert v.gate == "gating"
    assert v.live_state_verified is True  # concept judge scores live screenshots
    assert v.overall_score == 4.5


def test_yaml_verdict_explicit_fields_win_over_kind_defaults(tmp_path):
    p = tmp_path / "verdict-concept.yaml"
    p.write_text(
        yaml.dump(
            {
                "schema_version": 1,
                "kind": "concept",
                "gate": "advisory",
                "live_state_verified": True,
                "dimensions": {"concept_clarity": {"score": 4.0, "weight": 1.0}},
                "overall_score": 4.0,
                "verdict": "pass",
            }
        )
    )
    v = load_verdict(p)
    assert v.gate == "advisory"


def test_why_verdict_kind_inferred_from_filename(tmp_path):
    p = tmp_path / "verdict-why.yaml"
    _write_concept_yaml(p, overall=4.0)
    v = load_verdict(p)
    assert v.kind == "why"
    assert v.gate == "advisory"  # why-eval does not gate render convergence
    assert v.live_state_verified is False  # grades AI text against AI text


def test_explicit_kind_arg_overrides_filename(tmp_path):
    p = tmp_path / "some-verdict.yaml"
    _write_concept_yaml(p)
    v = load_verdict(p, kind="user_artifact")
    assert v.kind == "user_artifact"
    assert v.gate == "gating"


def test_unknown_filename_without_kind_raises(tmp_path):
    p = tmp_path / "mystery.yaml"
    _write_concept_yaml(p)
    with pytest.raises(ValueError):
        load_verdict(p)


# ---------------------------------------------------------------------------
# verdict-timing.json normalization
# ---------------------------------------------------------------------------


def test_timing_json_normalizes(tmp_path):
    p = tmp_path / "verdict-timing.json"
    p.write_text(
        json.dumps(
            {
                "verdict": "warn",
                "overallScore": 3.0,
                "coverage": 0.8,
                "findings": ["inversion: 'phone' spoken before field focused"],
            }
        )
    )
    v = load_verdict(p)
    assert v.kind == "timing"
    assert v.gate == "advisory"
    assert v.live_state_verified is True  # deterministic, measured off the real mp4
    assert v.overall_score == 3.0
    assert v.verdict == "warn"
    assert "field_sync" in v.dimensions
    assert "inversion" in (v.fix_recommendation or "")


def test_timing_null_verdict_returns_none(tmp_path):
    # dashboard/map walkthroughs with no narrated form fields: warp doesn't
    # engage, nothing to aggregate
    p = tmp_path / "verdict-timing.json"
    p.write_text(json.dumps({"verdict": None, "overallScore": None, "coverage": 0}))
    assert load_verdict(p) is None


# ---------------------------------------------------------------------------
# verdict-video.json normalization
# ---------------------------------------------------------------------------


def test_video_json_normalizes(tmp_path):
    p = tmp_path / "verdict-video.json"
    p.write_text(
        json.dumps(
            {
                "scenes": [
                    {
                        "beat": "scene_1",
                        "scores": {"vo_visual_coherence": 4, "pacing": 5},
                        "overall": 4.5,
                        "verdict": "pass",
                        "findings": [],
                    },
                    {
                        "beat": "scene_2",
                        "scores": {"vo_visual_coherence": 3, "pacing": 3},
                        "overall": 3.0,
                        "verdict": "warn",
                        "findings": [{"route": "NARRATION", "text": "VO outruns the form"}],
                    },
                ]
            }
        )
    )
    v = load_verdict(p)
    assert v.kind == "video"
    assert v.gate == "advisory"
    assert v.overall_score == 3.75  # mean of per-scene overalls
    assert v.verdict == "warn"  # worst scene's verdict
    assert v.dimensions["vo_visual_coherence"].score == 3.5  # mean across scenes
    assert v.dimensions["pacing"].score == 4.0


def test_video_json_empty_scenes_returns_none(tmp_path):
    p = tmp_path / "verdict-video.json"
    p.write_text(json.dumps({"scenes": []}))
    assert load_verdict(p) is None


# ---------------------------------------------------------------------------
# KIND_DEFAULTS is the single registry
# ---------------------------------------------------------------------------


def test_kind_defaults_covers_all_six_families():
    assert set(KIND_DEFAULTS) == {
        "concept",
        "user_artifact",
        "why",
        "actionability",
        "timing",
        "video",
    }
