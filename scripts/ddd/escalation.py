"""Self-tune tracker for DDD escalation decisions (SP6c).

State file: ``<ddd_dir>/escalation.json``
Resolved via ``_resolve_ddd_dir()`` from ``scripts.ddd.runstate``.

Shape::

    {
      "<decision_class>": {
        "accepted": int,
        "redirected": int,
        "streak": int,
        "downgraded": bool
      }
    }

The tracker is *propose-then-confirm* only: ``should_propose_downgrade``
signals readiness; ``mark_downgraded`` is called exclusively after explicit
user confirmation. Nothing is auto-applied.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.ddd.runstate import _resolve_ddd_dir


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_ENTRY: dict = {
    "accepted": 0,
    "redirected": 0,
    "streak": 0,
    "downgraded": False,
}


def _state_file() -> Path:
    return _resolve_ddd_dir() / "escalation.json"


def _load() -> dict:
    f = _state_file()
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def _save(data: dict) -> None:
    f = _state_file()
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _entry(data: dict, decision_class: str) -> dict:
    """Return a mutable default-initialised entry for *decision_class*."""
    if decision_class not in data:
        data[decision_class] = dict(_DEFAULT_ENTRY)
    return data[decision_class]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record(decision_class: str, accepted: bool) -> None:
    """Record one decision outcome.

    - *accepted*=True  → ``accepted += 1``, ``streak += 1``
    - *accepted*=False → ``redirected += 1``, ``streak = 0``
    """
    data = _load()
    e = _entry(data, decision_class)
    if accepted:
        e["accepted"] += 1
        e["streak"] += 1
    else:
        e["redirected"] += 1
        e["streak"] = 0
    _save(data)


def should_propose_downgrade(
    decision_class: str,
    *,
    threshold: int = 5,
) -> bool:
    """Return True iff ``streak >= threshold`` AND not already downgraded.

    This is the *proposal* trigger only — the orchestrator must ask the
    user to confirm before calling ``mark_downgraded``.
    """
    data = _load()
    e = _entry(data, decision_class)
    return e["streak"] >= threshold and not e["downgraded"]


def mark_downgraded(decision_class: str) -> None:
    """Persist ``downgraded = True`` for *decision_class*.

    Call this **only** after explicit user confirmation.
    """
    data = _load()
    e = _entry(data, decision_class)
    e["downgraded"] = True
    _save(data)


def is_downgraded(decision_class: str) -> bool:
    """Return True iff *decision_class* has been marked as downgraded."""
    data = _load()
    e = _entry(data, decision_class)
    return e["downgraded"]
