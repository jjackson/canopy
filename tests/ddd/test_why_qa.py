"""Behavioral tests for scripts/ddd/why_qa.py (SP1.3).

TDD: these tests are written first and drive the implementation.
why_qa(brief_obj_or_path) -> Verdict
  - "pass"  for a well-formed, grounded brief
  - "fail"  (with blocking_reason) when:
      * any spine item has empty rationale
      * a grounded item lacks non-assumed evidence
      * a Gap.claim_ref doesn't resolve to any SpineItem.id
      * problem is empty
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.ddd.schemas.models import (
    Evidence,
    Gap,
    SpineItem,
    Verdict,
    WhyBrief,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _brief(**kwargs) -> WhyBrief:
    """Build a minimal valid WhyBrief, override fields via kwargs."""
    defaults = dict(
        narrative_slug="F",
        problem="A real problem",
        spine=[
            SpineItem(
                id="S1",
                claim="Claim one",
                rationale="Because of evidence X",
                status="grounded",
                evidence=[Evidence(kind="documented", ref="doc://abc")],
            )
        ],
        gaps=[],
    )
    defaults.update(kwargs)
    return WhyBrief(**defaults)


def _write_brief(tmp_path: Path, brief: WhyBrief) -> Path:
    p = tmp_path / "why_brief.yaml"
    p.write_text(yaml.dump(brief.model_dump()))
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_well_formed_brief_passes():
    from scripts.ddd.why_qa import why_qa

    brief = _brief()
    result = why_qa(brief)
    assert isinstance(result, Verdict)
    assert result.verdict == "pass"
    assert result.blocking_reason is None


def test_well_formed_brief_from_path_passes(tmp_path):
    from scripts.ddd.why_qa import why_qa

    brief = _brief()
    path = _write_brief(tmp_path, brief)
    result = why_qa(path)
    assert result.verdict == "pass"


# ---------------------------------------------------------------------------
# Failure: empty problem
# ---------------------------------------------------------------------------

def test_empty_problem_fails():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(problem="")
    result = why_qa(brief)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
    assert "problem" in result.blocking_reason.lower()


def test_whitespace_only_problem_fails():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(problem="   ")
    result = why_qa(brief)
    assert result.verdict == "fail"


# ---------------------------------------------------------------------------
# Failure: empty rationale on spine item
# ---------------------------------------------------------------------------

def test_empty_rationale_fails():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(spine=[
        SpineItem(id="S1", claim="Claim", rationale="", status="gap")
    ])
    result = why_qa(brief)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
    assert "rationale" in result.blocking_reason.lower()


def test_whitespace_rationale_fails():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(spine=[
        SpineItem(id="S1", claim="Claim", rationale="   ", status="gap")
    ])
    result = why_qa(brief)
    assert result.verdict == "fail"


# ---------------------------------------------------------------------------
# Failure: grounded item with only assumed evidence
# ---------------------------------------------------------------------------

def test_grounded_only_assumed_evidence_fails():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(spine=[
        SpineItem(
            id="S1",
            claim="Claim",
            rationale="rationale here",
            status="grounded",
            evidence=[Evidence(kind="assumed", ref="someone assumed it")],
        )
    ])
    result = why_qa(brief)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
    assert "grounded" in result.blocking_reason.lower() or "evidence" in result.blocking_reason.lower()


def test_grounded_no_evidence_fails():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(spine=[
        SpineItem(
            id="S1",
            claim="Claim",
            rationale="rationale",
            status="grounded",
            evidence=[],
        )
    ])
    result = why_qa(brief)
    assert result.verdict == "fail"


def test_grounded_with_documented_evidence_passes():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(spine=[
        SpineItem(
            id="S1",
            claim="Claim",
            rationale="rationale",
            status="grounded",
            evidence=[Evidence(kind="documented", ref="doc://x")],
        )
    ])
    result = why_qa(brief)
    assert result.verdict == "pass"


def test_grounded_with_implemented_evidence_passes():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(spine=[
        SpineItem(
            id="S1",
            claim="Claim",
            rationale="rationale",
            status="grounded",
            evidence=[Evidence(kind="implemented", ref="code://src/module.py")],
        )
    ])
    result = why_qa(brief)
    assert result.verdict == "pass"


# ---------------------------------------------------------------------------
# Failure: Gap.claim_ref doesn't resolve
# ---------------------------------------------------------------------------

def test_gap_claim_ref_unresolved_fails():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(
        spine=[SpineItem(id="S1", claim="C", rationale="R", status="gap")],
        gaps=[
            Gap(
                id="G1",
                type="RESEARCH",
                claim_ref="S99",  # does not exist
                detail="detail",
                proposed_action="action",
            )
        ],
    )
    result = why_qa(brief)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
    assert "S99" in result.blocking_reason or "claim_ref" in result.blocking_reason.lower()


def test_gap_claim_ref_resolved_passes():
    from scripts.ddd.why_qa import why_qa

    brief = _brief(
        spine=[
            SpineItem(
                id="S1",
                claim="C",
                rationale="R",
                status="grounded",
                evidence=[Evidence(kind="documented", ref="doc://x")],
            )
        ],
        gaps=[
            Gap(
                id="G1",
                type="RESEARCH",
                claim_ref="S1",  # valid
                detail="detail",
                proposed_action="action",
            )
        ],
    )
    result = why_qa(brief)
    assert result.verdict == "pass"


# ---------------------------------------------------------------------------
# Multiple failures → blocking_reason mentions all
# ---------------------------------------------------------------------------

def test_multiple_failures_mentioned_in_blocking_reason():
    from scripts.ddd.why_qa import why_qa

    # Violates both: empty problem AND empty rationale on spine item
    brief = _brief(
        problem="",
        spine=[SpineItem(id="S1", claim="C", rationale="", status="gap")],
    )
    result = why_qa(brief)
    assert result.verdict == "fail"
    # Both issues should appear in blocking_reason
    assert result.blocking_reason is not None
    assert "problem" in result.blocking_reason.lower()
    assert "rationale" in result.blocking_reason.lower()


# ---------------------------------------------------------------------------
# Return type is always Verdict
# ---------------------------------------------------------------------------

def test_returns_verdict_model():
    from scripts.ddd.why_qa import why_qa
    from scripts.ddd.schemas.models import Verdict

    result = why_qa(_brief())
    assert isinstance(result, Verdict)
    assert result.schema_version == 1


# ---------------------------------------------------------------------------
# CLI: python -m scripts.ddd.why_qa <path> exits 0 on pass, 1 on fail
# ---------------------------------------------------------------------------

def test_cli_exit_0_on_valid(tmp_path):
    import subprocess, sys

    brief = _brief()
    path = _write_brief(tmp_path, brief)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.why_qa", str(path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr


def test_cli_exit_1_on_invalid(tmp_path):
    import subprocess, sys

    brief = _brief(problem="")
    path = _write_brief(tmp_path, brief)
    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.why_qa", str(path)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1


def test_cli_no_args_exits_2_usage():
    """Zero args → exit 2 (usage error)."""
    import subprocess, sys

    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.why_qa"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 2


def test_cli_bad_path_exits_1():
    """Bad/missing <path> argument → exit 1 (not a usage error)."""
    import subprocess, sys

    result = subprocess.run(
        [sys.executable, "-m", "scripts.ddd.why_qa", "/nonexistent/why_brief.yaml"],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Delegated checks: duplicate SpineItem.id (via validate.py)
# ---------------------------------------------------------------------------

def test_duplicate_spine_id_fails():
    """why_qa delegates to validate.py which catches duplicate spine ids."""
    from scripts.ddd.why_qa import why_qa

    brief = _brief(
        spine=[
            SpineItem(
                id="S1",
                claim="First claim",
                rationale="Rationale one",
                status="grounded",
                evidence=[Evidence(kind="documented", ref="doc://a")],
            ),
            SpineItem(
                id="S1",  # duplicate id — same as first item
                claim="Second claim",
                rationale="Rationale two",
                status="grounded",
                evidence=[Evidence(kind="documented", ref="doc://b")],
            ),
        ]
    )
    result = why_qa(brief)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
    assert "duplicate" in result.blocking_reason.lower() or "S1" in result.blocking_reason


# ---------------------------------------------------------------------------
# Library contract: missing / malformed input returns Verdict (does not raise)
# ---------------------------------------------------------------------------

def test_nonexistent_path_returns_fail_verdict():
    """why_qa(Path('/nonexistent.yaml')) returns a fail Verdict, does not raise."""
    from scripts.ddd.why_qa import why_qa

    result = why_qa(Path("/nonexistent.yaml"))
    assert isinstance(result, Verdict)
    assert result.verdict == "fail"
    assert result.blocking_reason is not None
