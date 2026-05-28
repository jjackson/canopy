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


def test_decision_default_dump_emits_class_not_class_underscore():
    """Regression: plain model_dump() / model_dump_json() must emit 'class', not 'class_'."""
    from scripts.ddd.schemas.models import Decision, ReviewRequest

    d = Decision(
        id="D1",
        prompt="Which approach?",
        options=["A", "B"],
        recommended="A",
        class_="SCOPE",
    )
    # Default model_dump() (no by_alias argument) must emit "class"
    plain_dump = d.model_dump()
    assert "class" in plain_dump, "model_dump() must emit 'class' key by default"
    assert "class_" not in plain_dump, "model_dump() must NOT emit 'class_' by default"

    # model_dump_json() must also emit "class"
    json_str = d.model_dump_json()
    assert '"class"' in json_str, "model_dump_json() must emit '\"class\"' by default"
    assert '"class_"' not in json_str, "model_dump_json() must NOT emit '\"class_\"' by default"

    # And through ReviewRequest (the real consumer path)
    rr = ReviewRequest(
        run_id="run-001",
        gate="phase1",
        video={"url": "http://example.com/v.mp4"},
        decisions=[d],
        narration=[{"text": "hello"}],
    )
    rr_json = rr.model_dump_json()
    assert '"class"' in rr_json, "ReviewRequest.model_dump_json() must emit '\"class\"'"
    assert '"class_"' not in rr_json, "ReviewRequest.model_dump_json() must NOT emit '\"class_\"'"


def test_decision_loads_from_class_key_and_class_kwarg():
    """Decision must accept both {'class': ...} dict input and class_=... kwarg."""
    from scripts.ddd.schemas.models import Decision

    # Load from dict with "class" key (JSON/YAML deserialization path)
    d1 = Decision.model_validate({
        "id": "D1",
        "prompt": "p",
        "options": ["A"],
        "recommended": "A",
        "class": "SCOPE",
    })
    assert d1.class_ == "SCOPE"

    # Load using Python kwarg class_=
    d2 = Decision(
        id="D2",
        prompt="p",
        options=["A"],
        recommended="A",
        class_="SCOPE",
    )
    assert d2.class_ == "SCOPE"
