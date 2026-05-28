"""Tests for DDD schema models (SP0.1 + SP0.2)."""
import pytest
import pydantic


# ---------------------------------------------------------------------------
# SP0.1 — WhyBrief schema
# ---------------------------------------------------------------------------

def test_why_brief_round_trip():
    from scripts.ddd.schemas.models import WhyBrief, SpineItem, Gap

    wb = WhyBrief(
        feature="Rooftop Survey Sampling",
        problem="We lack a systematic way to sample rooftops.",
        spine=[
            SpineItem(id="S1", claim="Sampling is needed", rationale="without it we miss units"),
        ],
        gaps=[
            Gap(
                id="G1",
                type="RESEARCH",
                claim_ref="S1",
                detail="No baseline data",
                proposed_action="commission survey",
            )
        ],
    )
    d = wb.model_dump()
    assert d["schema_version"] == 1
    assert d["feature"] == "Rooftop Survey Sampling"
    assert d["spine"][0]["id"] == "S1"
    assert d["gaps"][0]["type"] == "RESEARCH"


def test_gap_invalid_type_raises():
    from scripts.ddd.schemas.models import Gap

    with pytest.raises(pydantic.ValidationError):
        Gap(
            id="G1",
            type="BOGUS",
            claim_ref="S1",
            detail="x",
            proposed_action="y",
        )


# ---------------------------------------------------------------------------
# SP0.2 — Remaining models
# ---------------------------------------------------------------------------

def test_scene_missing_required_fields_raises():
    from scripts.ddd.schemas.models import Scene

    with pytest.raises(pydantic.ValidationError):
        # concept_claim and provenance are both missing
        Scene(persona="p1", title="My Scene", show="navigate to /home")


def test_verdict_invalid_verdict_raises():
    from scripts.ddd.schemas.models import Verdict, Dimension

    with pytest.raises(pydantic.ValidationError):
        Verdict(
            dimensions={"clarity": Dimension(score=7.0, weight=1.0)},
            overall_score=7.0,
            verdict="bogus",
        )


def test_verdict_valid_pass():
    from scripts.ddd.schemas.models import Verdict, Dimension

    v = Verdict(
        dimensions={"clarity": Dimension(score=8.0, weight=1.0)},
        overall_score=8.0,
        verdict="pass",
    )
    assert v.verdict == "pass"
    assert v.schema_version == 1
    assert v.blocking_reason is None
    assert v.fix_recommendation is None


def test_decision_serializes_class_as_alias():
    from scripts.ddd.schemas.models import Decision

    d = Decision(
        id="D1",
        prompt="Which approach?",
        options=["A", "B"],
        recommended="A",
        class_="SCOPE",
    )
    dumped = d.model_dump(by_alias=True)
    assert "class" in dumped
    assert dumped["class"] == "SCOPE"
    # Should not have the Python name "class_" in aliased output
    assert "class_" not in dumped
