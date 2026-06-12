"""Schema tests for ``SetupBlock`` / ``UnifiedSpec.setup`` (the data-setup contract).

Pins the new optional ``setup:`` block on the spec: a synthetic-generator
command that runs before rendering, the outputs JSON it emits, the
``per_render | once`` rerun semantics, and back-compat (specs without a
setup block keep validating unchanged).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.narrative.models import SetupBlock, UnifiedSpec  # noqa: E402

_SPEC_BASE = dict(
    name="par-demo",
    narrative="A program admin reviews flagged visits and creates an audit.",
    base_url="https://labs.connect.dimagi.com",
    personas={
        "dana": {
            "name": "Dana",
            "role": "Program Admin",
            "color": "#2563eb",
            "intro": "Dana reviews program performance weekly.",
        }
    },
    scenes=[],
)


def test_setup_block_defaults():
    s = SetupBlock.model_validate({"command": "python scripts/walkthroughs/par/regenerate.py"})
    assert s.outputs is None
    assert s.rerun == "per_render"          # state-mutating-safe default
    assert s.timeout_seconds == 1200


def test_setup_block_full():
    s = SetupBlock.model_validate(
        {
            "command": "python scripts/walkthroughs/par/regenerate.py",
            "outputs": "scripts/walkthroughs/par/outputs.json",
            "rerun": "once",
            "timeout_seconds": 300,
        }
    )
    assert s.outputs == "scripts/walkthroughs/par/outputs.json"
    assert s.rerun == "once"
    assert s.timeout_seconds == 300


def test_setup_block_rejects_unknown_rerun():
    with pytest.raises(ValidationError):
        SetupBlock.model_validate({"command": "true", "rerun": "sometimes"})


def test_unified_spec_setup_defaults_to_none():
    """Existing specs with no ``setup:`` keep validating (back-compat)."""
    spec = UnifiedSpec.model_validate(_SPEC_BASE)
    assert spec.setup is None


def test_unified_spec_accepts_setup_block():
    spec = UnifiedSpec.model_validate(
        {
            **_SPEC_BASE,
            "setup": {
                "command": "python scripts/walkthroughs/par/regenerate.py",
                "outputs": "scripts/walkthroughs/par/outputs.json",
            },
        }
    )
    assert isinstance(spec.setup, SetupBlock)
    assert spec.setup.rerun == "per_render"
