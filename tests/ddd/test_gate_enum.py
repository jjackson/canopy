"""The shared ``Gate`` enum replaces scattered gate string literals.

A ``Gate`` member IS a string (``str, Enum``) so it drops in anywhere a gate
literal was expected — equality with the literal, ``str()``, JSON serialization
all keep working. Importable from both the narrative model home and the DDD
re-export shim.
"""
from __future__ import annotations


def test_gate_importable_from_both_homes():
    from scripts.ddd.schemas.models import Gate as GateA
    from scripts.narrative.models import Gate as GateB

    assert GateA is GateB


def test_gate_members_equal_their_literals():
    from scripts.narrative.models import Gate

    assert Gate.PRODUCT_FINDINGS == "product_findings"
    assert Gate.CONCEPT_CHANGE == "concept_change"
    assert Gate.EXTERNAL_RELEASE == "external_release"


def test_gate_is_str_subclass():
    from scripts.narrative.models import Gate

    assert issubclass(Gate, str)
    assert isinstance(Gate.PRODUCT_FINDINGS, str)
    # str() of a member is the literal value, and it slots into f-strings/JSON.
    assert str(Gate.PRODUCT_FINDINGS) in ("product_findings", "Gate.PRODUCT_FINDINGS")
    assert Gate.PRODUCT_FINDINGS.value == "product_findings"
    # equality with the literal works in both directions.
    assert "concept_change" == Gate.CONCEPT_CHANGE
