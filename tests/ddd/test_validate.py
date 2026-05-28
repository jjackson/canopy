"""Tests for DDD validators (SP0.3)."""
import json
import shutil
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


# ---------------------------------------------------------------------------
# Fix 3a: duplicate SpineItem.id → problem
# ---------------------------------------------------------------------------

def test_duplicate_spine_id_fails(tmp_path):
    from scripts.ddd.validate import validate

    data = {
        "schema_version": 1,
        "feature": "F",
        "problem": "P",
        "spine": [
            {"id": "S1", "claim": "C1", "rationale": "R1"},
            {"id": "S1", "claim": "C2", "rationale": "R2"},  # duplicate
        ],
        "gaps": [],
    }
    path = _write_yaml(tmp_path, "why_brief.yaml", data)
    ok, problems = validate("why_brief", path)
    assert ok is False
    assert any("duplicate" in p.lower() and "S1" in p for p in problems)


# ---------------------------------------------------------------------------
# Fix 3b: Scene.persona not in personas → problem (even with no why_brief)
# ---------------------------------------------------------------------------

def test_scene_persona_not_in_personas_fails(tmp_path):
    from scripts.ddd.validate import validate

    spec_data = {
        "name": "Spec",
        "narrative": "n",
        "base_url": "http://localhost",
        # No why_brief declared
        "personas": {
            "alice": {"name": "Alice", "role": "PM", "color": "#fff", "intro": "Hi"}
        },
        "scenes": [
            {
                "persona": "bob",  # NOT in personas
                "title": "Dashboard",
                "show": "navigate to /",
                "concept_claim": "Works",
                "provenance": "S1",
            }
        ],
    }
    path = _write_yaml(tmp_path, "spec.yaml", spec_data)
    ok, problems = validate("unified_spec", path)
    assert ok is False
    assert any("bob" in p and "persona" in p.lower() for p in problems)


def test_scene_persona_valid_passes(tmp_path):
    from scripts.ddd.validate import validate

    spec_data = {
        "name": "Spec",
        "narrative": "n",
        "base_url": "http://localhost",
        "personas": {
            "alice": {"name": "Alice", "role": "PM", "color": "#fff", "intro": "Hi"}
        },
        "scenes": [
            {
                "persona": "alice",  # valid
                "title": "Dashboard",
                "show": "navigate to /",
                "concept_claim": "Works",
                "provenance": "S1",
            }
        ],
    }
    path = _write_yaml(tmp_path, "spec.yaml", spec_data)
    ok, problems = validate("unified_spec", path)
    assert ok is True
    assert problems == []


# ---------------------------------------------------------------------------
# Fix 3c: why_brief declared but unresolvable → problem (not silent skip)
# ---------------------------------------------------------------------------

def test_why_brief_declared_but_missing_file_fails(tmp_path):
    from scripts.ddd.validate import validate

    spec_data = {
        "name": "Spec",
        "narrative": "n",
        "base_url": "http://localhost",
        "why_brief": "nonexistent_why_brief.yaml",  # file doesn't exist
        "personas": {
            "alice": {"name": "Alice", "role": "PM", "color": "#fff", "intro": "Hi"}
        },
        "scenes": [
            {
                "persona": "alice",
                "title": "Dashboard",
                "show": "navigate to /",
                "concept_claim": "Works",
                "provenance": "S1",
            }
        ],
    }
    path = _write_yaml(tmp_path, "spec.yaml", spec_data)
    ok, problems = validate("unified_spec", path)
    assert ok is False
    assert any("why_brief" in p.lower() for p in problems)


def test_why_brief_not_declared_skips_provenance_check(tmp_path):
    """When no why_brief is declared at all, provenance check is skipped."""
    from scripts.ddd.validate import validate

    spec_data = {
        "name": "Spec",
        "narrative": "n",
        "base_url": "http://localhost",
        # why_brief is absent / None — skip provenance cross-check
        "personas": {
            "alice": {"name": "Alice", "role": "PM", "color": "#fff", "intro": "Hi"}
        },
        "scenes": [
            {
                "persona": "alice",
                "title": "Dashboard",
                "show": "navigate to /",
                "concept_claim": "Works",
                "provenance": "ANYTHING",  # unchecked when no why_brief
            }
        ],
    }
    path = _write_yaml(tmp_path, "spec.yaml", spec_data)
    ok, problems = validate("unified_spec", path)
    assert ok is True


# ---------------------------------------------------------------------------
# Fix 4: over-broad exception — programming errors should surface
# ---------------------------------------------------------------------------

def test_genuine_programming_error_surfaces(monkeypatch, tmp_path):
    """A genuine bug (e.g. NameError) must NOT be silently swallowed."""
    import scripts.ddd.validate as v_module

    original = v_module._semantic_why_brief

    def buggy(obj):
        raise RuntimeError("deliberate bug")  # not ValidationError/YAMLError/OSError

    monkeypatch.setattr(v_module, "_semantic_why_brief", buggy)

    data = {
        "schema_version": 1,
        "feature": "F",
        "problem": "P",
        "spine": [{"id": "S1", "claim": "C", "rationale": "R"}],
        "gaps": [],
    }
    path = _write_yaml(tmp_path, "why_brief.yaml", data)

    with pytest.raises(RuntimeError, match="deliberate bug"):
        v_module.validate("why_brief", path)


# ---------------------------------------------------------------------------
# Fix 5d: schema-drift test — committed JSON schemas match regenerated ones
# ---------------------------------------------------------------------------

def test_committed_json_schemas_match_generated(tmp_path):
    """Regenerate JSON schemas into tmp_path and assert they equal the committed files."""
    from scripts.ddd.validate import dump_json_schemas

    dump_json_schemas(out_dir=tmp_path)

    committed_dir = Path("scripts/ddd/schemas/json")
    for generated in sorted(tmp_path.glob("*.json")):
        committed = committed_dir / generated.name
        assert committed.exists(), f"Committed schema missing: {committed}"
        assert json.loads(generated.read_text()) == json.loads(committed.read_text()), (
            f"Schema drift detected in {committed.name}: "
            "committed file differs from what would be regenerated"
        )


# ---------------------------------------------------------------------------
# Fix 5e: validate() on missing file and malformed YAML → (False, [non-empty])
# ---------------------------------------------------------------------------

def test_validate_missing_file_returns_false(tmp_path):
    from scripts.ddd.validate import validate

    missing = tmp_path / "does_not_exist.yaml"
    ok, problems = validate("why_brief", missing)
    assert ok is False
    assert len(problems) > 0


def test_validate_malformed_yaml_returns_false(tmp_path):
    from scripts.ddd.validate import validate

    bad = tmp_path / "bad.yaml"
    bad.write_text("this: is: not: valid: yaml: :\n  - broken [indent")
    ok, problems = validate("why_brief", bad)
    assert ok is False
    assert len(problems) > 0


# ---------------------------------------------------------------------------
# Fix 5f: pydantic errors formatted as "loc: msg" not raw repr dicts
# ---------------------------------------------------------------------------

def test_validation_error_format_is_readable(tmp_path):
    """Pydantic errors must be formatted as 'field: message', not raw dict reprs."""
    from scripts.ddd.validate import validate

    # Missing required fields in why_brief
    data = {"schema_version": 1}  # missing feature, problem, spine, gaps
    path = _write_yaml(tmp_path, "why_brief.yaml", data)
    ok, problems = validate("why_brief", path)
    assert ok is False
    # None of the problem strings should look like a raw Python dict repr
    for p in problems:
        assert not p.startswith("{'"), f"Problem looks like raw dict repr: {p!r}"
        assert not p.startswith('{"'), f"Problem looks like raw JSON repr: {p!r}"
        # Should contain a colon separating location from message
        assert ":" in p, f"Problem lacks 'loc: msg' format: {p!r}"
