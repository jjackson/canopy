"""Guard test: ACTION_KINDS lives only in scripts/ddd/schemas/models.py.

The recorder imports it from there. This test fails fast if the two ever
drift — adding a verb to the schema without wiring the dispatcher should
flag here, and vice versa.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.ddd.schemas.models import ACTION_KINDS as SCHEMA_KINDS  # noqa: E402
from scripts.walkthrough._lib.recorder import ACTION_KINDS as RECORDER_KINDS  # noqa: E402


def test_recorder_and_schema_agree():
    assert tuple(SCHEMA_KINDS) == tuple(RECORDER_KINDS)


def test_action_pydantic_literal_matches_action_kinds():
    """The Pydantic Literal in Action.kind must enumerate the same set.

    We can't unpack a tuple into ``Literal[...]`` at class-definition time on
    every Python version, so the Literal is hardcoded. This test catches the
    drift that hardcoding allows.
    """
    from typing import get_args

    from scripts.ddd.schemas.models import Action

    kind_field = Action.model_fields["kind"]
    literal_args = set(get_args(kind_field.annotation))
    assert literal_args == set(SCHEMA_KINDS), (
        f"Action.kind Literal disagrees with ACTION_KINDS: "
        f"only in Literal={literal_args - set(SCHEMA_KINDS)}, "
        f"only in ACTION_KINDS={set(SCHEMA_KINDS) - literal_args}"
    )
