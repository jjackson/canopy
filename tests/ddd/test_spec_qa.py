"""Behavioral tests for scripts/ddd/spec_qa.py (SP2.2).

TDD: these tests are written first and drive the implementation.
spec_qa(spec_obj_or_path, why_brief_path=None) -> Verdict
  - "pass"  for a well-formed spec with no vacuous concept_claims
  - "fail"  (with blocking_reason) when:
      * a scene has an empty/whitespace concept_claim
      * a scene has a vacuous concept_claim (banned marketing phrases)
      * a scene's provenance doesn't match any spine id (via delegation)
      * a scene references an undefined persona (via delegation)
      * a required field is missing (via delegation)
  - Always returns Verdict (never raises) on missing/malformed input
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _why_brief_data(spine_ids: list[str] | None = None) -> dict:
    """Build a minimal valid WhyBrief dict."""
    if spine_ids is None:
        spine_ids = ["S1"]
    spine = [
        {
            "id": sid,
            "claim": f"Claim {sid}",
            "rationale": f"Because of evidence for {sid}",
            "status": "grounded",
            "evidence": [{"kind": "documented", "ref": f"doc://{sid}"}],
        }
        for sid in spine_ids
    ]
    return {
        "schema_version": 1,
        "feature": "Test Feature",
        "problem": "A real problem exists for users",
        "spine": spine,
        "gaps": [],
    }


def _spec_data(
    concept_claim: str = "Users can submit a form and see confirmation within 2 seconds",
    provenance: str = "S1",
    persona_key: str = "alice",
    why_brief_rel: str | None = None,
) -> dict:
    """Build a minimal valid UnifiedSpec dict."""
    return {
        "name": "My Feature Walkthrough",
        "narrative": "Demonstrates the core user journey",
        "base_url": "http://localhost:8000",
        "why_brief": why_brief_rel,
        "personas": {
            persona_key: {
                "name": "Alice",
                "role": "Program Manager",
                "color": "#3B82F6",
                "intro": "Alice manages program delivery.",
            }
        },
        "scenes": [
            {
                "persona": persona_key,
                "title": "Submit Form",
                "show": "navigate to /form, fill fields, click Submit",
                "concept_claim": concept_claim,
                "provenance": provenance,
                "design_intent": "Test that confirmation feedback is immediate",
            }
        ],
    }


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(yaml.dump(data))
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_spec_no_why_brief_passes():
    """A valid spec with no why_brief link passes."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data()  # no why_brief linked
    result = spec_qa(spec)
    assert result.verdict == "pass"
    assert result.blocking_reason is None


def test_valid_spec_with_why_brief_passes(tmp_path):
    """A valid spec with a resolvable why_brief and matching provenance passes."""
    from scripts.ddd.spec_qa import spec_qa

    wb_path = _write_yaml(tmp_path, "why_brief.yaml", _why_brief_data(["S1"]))
    spec = _spec_data(provenance="S1", why_brief_rel="why_brief.yaml")
    spec_path = _write_yaml(tmp_path, "spec.yaml", spec)

    result = spec_qa(spec_path, why_brief_path=str(wb_path))
    assert result.verdict == "pass"
    assert result.blocking_reason is None


def test_valid_spec_from_path_passes(tmp_path):
    """spec_qa accepts a file path."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data()
    spec_path = _write_yaml(tmp_path, "spec.yaml", spec)
    result = spec_qa(spec_path)
    assert result.verdict == "pass"


# ---------------------------------------------------------------------------
# Failure: vacuous concept_claim (banned marketing phrases)
# ---------------------------------------------------------------------------

def test_vacuous_claim_world_class_fails():
    """A concept_claim containing 'world-class' is not falsifiable → fail."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(concept_claim="a world-class seamless experience")
    result = spec_qa(spec)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
    assert "concept_claim" in result.blocking_reason.lower() or "falsifiable" in result.blocking_reason.lower()


def test_vacuous_claim_seamless_fails():
    """A concept_claim containing 'seamless' is not falsifiable → fail."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(concept_claim="Provides a seamless workflow for users")
    result = spec_qa(spec)
    assert result.verdict == "fail"


def test_vacuous_claim_powerful_fails():
    """A concept_claim containing 'powerful' is not falsifiable → fail."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(concept_claim="A powerful tool that empowers users")
    result = spec_qa(spec)
    assert result.verdict == "fail"


def test_vacuous_claim_robust_fails():
    """A concept_claim containing 'robust' is not falsifiable → fail."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(concept_claim="Robust error handling")
    result = spec_qa(spec)
    assert result.verdict == "fail"


def test_vacuous_claim_best_in_class_fails():
    """A concept_claim containing 'best-in-class' is not falsifiable → fail."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(concept_claim="best-in-class performance")
    result = spec_qa(spec)
    assert result.verdict == "fail"


def test_vacuous_claim_no_verb_fails():
    """A concept_claim with no verb is not falsifiable → fail."""
    from scripts.ddd.spec_qa import spec_qa

    # A noun phrase with no action/verb
    spec = _spec_data(concept_claim="fast loading")
    result = spec_qa(spec)
    assert result.verdict == "fail"


def test_empty_concept_claim_fails():
    """Empty concept_claim → fail."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(concept_claim="")
    result = spec_qa(spec)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None


def test_whitespace_concept_claim_fails():
    """Whitespace-only concept_claim → fail."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(concept_claim="   ")
    result = spec_qa(spec)
    assert result.verdict == "fail"


def test_falsifiable_claim_with_measurable_outcome_passes():
    """A claim with a specific measurable outcome passes."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(
        concept_claim="When a supervisor submits the audit form, the FLW receives a coaching task within 60 seconds"
    )
    result = spec_qa(spec)
    assert result.verdict == "pass"


def test_falsifiable_claim_with_verb_passes():
    """A claim describing a user action with a concrete result passes."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(
        concept_claim="Users can filter the task list by status and see only open tasks"
    )
    result = spec_qa(spec)
    assert result.verdict == "pass"


# ---------------------------------------------------------------------------
# Failure: provenance mismatch (via delegation to validate)
# ---------------------------------------------------------------------------

def test_provenance_mismatch_fails(tmp_path):
    """A scene whose provenance doesn't match any spine id → fail (delegation)."""
    from scripts.ddd.spec_qa import spec_qa

    wb_path = _write_yaml(tmp_path, "why_brief.yaml", _why_brief_data(["S1"]))
    spec = _spec_data(
        provenance="S99",  # does not exist in why_brief
        why_brief_rel="why_brief.yaml",
    )
    spec_path = _write_yaml(tmp_path, "spec.yaml", spec)

    result = spec_qa(spec_path)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
    assert "S99" in result.blocking_reason or "provenance" in result.blocking_reason.lower()


# ---------------------------------------------------------------------------
# Failure: undefined persona (via delegation to validate)
# ---------------------------------------------------------------------------

def test_undefined_persona_fails():
    """A scene referencing an undefined persona → fail (delegation)."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data(persona_key="alice")
    # manually break: scene references 'bob' but only 'alice' is defined
    spec["scenes"][0]["persona"] = "bob"
    result = spec_qa(spec)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
    assert "persona" in result.blocking_reason.lower() or "bob" in result.blocking_reason


# ---------------------------------------------------------------------------
# Failure: missing required field (via delegation to validate)
# ---------------------------------------------------------------------------

def test_missing_base_url_fails():
    """Missing required field (base_url) → fail (delegation)."""
    from scripts.ddd.spec_qa import spec_qa

    spec = _spec_data()
    del spec["base_url"]
    result = spec_qa(spec)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None


# ---------------------------------------------------------------------------
# Missing / malformed input: returns Verdict (never raises)
# ---------------------------------------------------------------------------

def test_missing_file_returns_fail_verdict():
    """spec_qa(Path('/nonexistent.yaml')) returns fail Verdict, does not raise."""
    from scripts.ddd.spec_qa import spec_qa
    from scripts.ddd.schemas.models import Verdict

    result = spec_qa(Path("/nonexistent/spec.yaml"))
    assert isinstance(result, Verdict)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None


def test_malformed_yaml_returns_fail_verdict(tmp_path):
    """A malformed YAML file returns fail Verdict, does not raise."""
    from scripts.ddd.spec_qa import spec_qa
    from scripts.ddd.schemas.models import Verdict

    bad = tmp_path / "bad.yaml"
    bad.write_text("this: is: not: valid: yaml: :\n  - broken [indent")
    result = spec_qa(bad)
    assert isinstance(result, Verdict)
    assert result.verdict == "fail"


def test_none_dict_returns_fail_verdict():
    """spec_qa(None) returns fail Verdict, does not raise."""
    from scripts.ddd.spec_qa import spec_qa
    from scripts.ddd.schemas.models import Verdict

    result = spec_qa(None)  # type: ignore[arg-type]
    assert isinstance(result, Verdict)
    assert result.verdict == "fail"


def test_always_returns_verdict_model():
    """Return type is always Verdict."""
    from scripts.ddd.spec_qa import spec_qa
    from scripts.ddd.schemas.models import Verdict

    result = spec_qa(_spec_data())
    assert isinstance(result, Verdict)
    assert result.schema_version == 1


# ---------------------------------------------------------------------------
# Confirms delegation to validate() — not re-implemented here
# ---------------------------------------------------------------------------

def test_delegates_to_validate_for_provenance_check(tmp_path):
    """Provenance cross-check is done by validate(), not spec_qa's own code."""
    from scripts.ddd.spec_qa import spec_qa

    # Create a why_brief with S1 only
    wb_path = _write_yaml(tmp_path, "why_brief.yaml", _why_brief_data(["S1"]))
    # Create spec that references S2 (which doesn't exist)
    spec = _spec_data(provenance="S2", why_brief_rel="why_brief.yaml")
    spec_path = _write_yaml(tmp_path, "spec.yaml", spec)

    result = spec_qa(spec_path)
    assert result.verdict == "fail"
    # The error mentions S2, proving validate() caught it
    assert result.blocking_reason is not None
    assert "S2" in result.blocking_reason or "provenance" in result.blocking_reason.lower()


# ---------------------------------------------------------------------------
# CLI: python -m scripts.ddd.spec_qa exits 0 on pass, 1 on fail, 2 on usage
# ---------------------------------------------------------------------------

def test_cli_exit_0_on_valid(tmp_path):
    import subprocess
    import sys

    spec = _spec_data()
    spec_path = _write_yaml(tmp_path, "spec.yaml", spec)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.spec_qa", str(spec_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cli_exit_1_on_invalid(tmp_path):
    import subprocess
    import sys

    spec = _spec_data(concept_claim="seamless world-class experience")
    spec_path = _write_yaml(tmp_path, "spec.yaml", spec)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.spec_qa", str(spec_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1


def test_cli_no_args_exits_2():
    """Zero args → exit 2 (usage error)."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.spec_qa"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


def test_cli_bad_path_exits_1():
    """Non-existent path → exit 1 (not a usage error)."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.spec_qa", "/nonexistent/spec.yaml"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1


def test_cli_with_why_brief_arg_exit_0(tmp_path):
    """CLI accepts optional second arg: why_brief path."""
    import subprocess
    import sys

    wb_path = _write_yaml(tmp_path, "why_brief.yaml", _why_brief_data(["S1"]))
    spec = _spec_data(provenance="S1", why_brief_rel="why_brief.yaml")
    spec_path = _write_yaml(tmp_path, "spec.yaml", spec)

    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.spec_qa", str(spec_path), str(wb_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
