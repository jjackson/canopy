"""Tests for DDD validators (SP0.3)."""
import json
from pathlib import Path

import pytest
import yaml


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data))
    return p


# ---------------------------------------------------------------------------
# Basic validation — valid why_brief
# ---------------------------------------------------------------------------

def test_valid_why_brief_returns_true(tmp_path):
    from scripts.ddd.validate import validate

    data = {
        "schema_version": 1,
        "feature": "Sampling",
        "problem": "no systematic sampling",
        "spine": [
            {
                "id": "S1",
                "claim": "Sampling needed",
                "rationale": "needed",
                "status": "gap",
            }
        ],
        "gaps": [
            {
                "id": "G1",
                "type": "RESEARCH",
                "claim_ref": "S1",
                "detail": "no data",
                "proposed_action": "survey",
            }
        ],
    }
    path = _write_yaml(tmp_path, "why_brief.yaml", data)
    ok, problems = validate("why_brief", path)
    assert ok is True
    assert problems == []


# ---------------------------------------------------------------------------
# Semantic rule (a): grounded spine item with no real evidence → invalid
# ---------------------------------------------------------------------------

def test_grounded_spine_without_evidence_fails(tmp_path):
    from scripts.ddd.validate import validate

    data = {
        "schema_version": 1,
        "feature": "F",
        "problem": "P",
        "spine": [
            {
                "id": "S1",
                "claim": "C",
                "rationale": "R",
                "status": "grounded",
                "evidence": [],  # no evidence at all
            }
        ],
        "gaps": [],
    }
    path = _write_yaml(tmp_path, "why_brief.yaml", data)
    ok, problems = validate("why_brief", path)
    assert ok is False
    assert len(problems) > 0


def test_grounded_spine_only_assumed_evidence_fails(tmp_path):
    from scripts.ddd.validate import validate

    data = {
        "schema_version": 1,
        "feature": "F",
        "problem": "P",
        "spine": [
            {
                "id": "S1",
                "claim": "C",
                "rationale": "R",
                "status": "grounded",
                "evidence": [{"kind": "assumed", "ref": "someone assumed it"}],
            }
        ],
        "gaps": [],
    }
    path = _write_yaml(tmp_path, "why_brief.yaml", data)
    ok, problems = validate("why_brief", path)
    assert ok is False
    assert len(problems) > 0


def test_grounded_spine_with_documented_evidence_passes(tmp_path):
    from scripts.ddd.validate import validate

    data = {
        "schema_version": 1,
        "feature": "F",
        "problem": "P",
        "spine": [
            {
                "id": "S1",
                "claim": "C",
                "rationale": "R",
                "status": "grounded",
                "evidence": [{"kind": "documented", "ref": "doc://thing"}],
            }
        ],
        "gaps": [],
    }
    path = _write_yaml(tmp_path, "why_brief.yaml", data)
    ok, problems = validate("why_brief", path)
    assert ok is True
    assert problems == []


# ---------------------------------------------------------------------------
# Semantic rule (b): scene.provenance must match a SpineItem.id
# ---------------------------------------------------------------------------

def test_scene_provenance_mismatch_fails(tmp_path):
    from scripts.ddd.validate import validate

    # Write why_brief
    wb_data = {
        "schema_version": 1,
        "feature": "F",
        "problem": "P",
        "spine": [{"id": "S1", "claim": "C", "rationale": "R", "status": "gap"}],
        "gaps": [],
    }
    wb_path = _write_yaml(tmp_path, "why_brief.yaml", wb_data)

    # Write unified_spec referencing why_brief via relative path
    spec_data = {
        "name": "My Spec",
        "narrative": "n",
        "base_url": "http://localhost",
        "why_brief": "why_brief.yaml",  # relative to spec file
        "personas": {
            "alice": {"name": "Alice", "role": "PM", "color": "#fff", "intro": "Hi"}
        },
        "scenes": [
            {
                "persona": "alice",
                "title": "Login",
                "show": "navigate to /login",
                "concept_claim": "Users can log in",
                "provenance": "S99",  # WRONG — no SpineItem with id S99
            }
        ],
    }
    spec_path = _write_yaml(tmp_path, "spec.yaml", spec_data)
    ok, problems = validate("unified_spec", spec_path)
    assert ok is False
    assert any("S99" in p or "provenance" in p.lower() for p in problems)


# ---------------------------------------------------------------------------
# Semantic rule (c): Gap.claim_ref must resolve to a SpineItem.id
# ---------------------------------------------------------------------------

def test_gap_claim_ref_missing_fails(tmp_path):
    from scripts.ddd.validate import validate

    data = {
        "schema_version": 1,
        "feature": "F",
        "problem": "P",
        "spine": [{"id": "S1", "claim": "C", "rationale": "R"}],
        "gaps": [
            {
                "id": "G1",
                "type": "RESEARCH",
                "claim_ref": "S99",  # WRONG
                "detail": "d",
                "proposed_action": "a",
            }
        ],
    }
    path = _write_yaml(tmp_path, "why_brief.yaml", data)
    ok, problems = validate("why_brief", path)
    assert ok is False
    assert len(problems) > 0
