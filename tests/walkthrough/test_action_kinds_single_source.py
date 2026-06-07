"""Guard test: ACTION_KINDS is the single source of truth.

Three places used to know about the action verb vocabulary independently —
the recorder dispatcher (``ACTION_KINDS`` tuple), the Pydantic ``Action.kind``
Literal, and the doc-comment list in ``Action``'s docstring. This test pins
all three to one source so a new verb can't ship to one and quietly skip the
others.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import get_args

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.narrative.models import ACTION_CLASSES, ACTION_KINDS as SCHEMA_KINDS  # noqa: E402
from scripts.walkthrough._lib.recorder import ACTION_KINDS as RECORDER_KINDS  # noqa: E402


def test_recorder_and_schema_agree():
    assert tuple(SCHEMA_KINDS) == tuple(RECORDER_KINDS)


def test_per_kind_classes_cover_every_kind():
    """Every action verb in ACTION_KINDS has a Pydantic subclass.

    With the discriminated union, missing a per-kind class would mean specs
    using that verb can never validate (the union has nothing to dispatch to).
    """
    declared = set()
    for cls in ACTION_CLASSES:
        kind_field = cls.model_fields["kind"]
        # Each subclass declares kind: Literal["foo"] — exactly one literal arg.
        literal_args = get_args(kind_field.annotation)
        assert len(literal_args) == 1, (
            f"{cls.__name__}.kind should be a single-arg Literal, got {literal_args}"
        )
        declared.add(literal_args[0])
    assert declared == set(SCHEMA_KINDS), (
        f"ACTION_CLASSES kinds disagree with ACTION_KINDS: "
        f"only in classes={declared - set(SCHEMA_KINDS)}, "
        f"only in ACTION_KINDS={set(SCHEMA_KINDS) - declared}"
    )


def test_action_classes_count_matches_action_kinds():
    """One class per kind, exactly — no orphans, no duplicates."""
    assert len(ACTION_CLASSES) == len(SCHEMA_KINDS)
