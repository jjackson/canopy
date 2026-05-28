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
