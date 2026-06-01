"""Action results + run report for the walkthrough recorder.

Before this module the recorder swallowed failures: a missing click target
printed a warning, the video showed a cursor twitching in place, and the run
reported success. The microplans-10-wards recording shipped at ``Created 0 of
10 plans · 10 errors`` looking fine from the outside until someone checked
plan counts on labs.

Now every action returns an :class:`ActionResult`. The orchestrator
accumulates them in a :class:`RunReport` and prints a per-scene + per-run
summary so silent failures stop hiding. Specs can also set
``must_succeed: true`` on an action; the runner raises instead of swallowing,
turning the recording into a quasi-test.

Error kinds (the ``error_kind`` field) are tagged so a downstream grader can
distinguish "target not found" (a spec drift bug — the UI changed) from
"playwright timeout" (a flaky page) from "unknown_kind" (a spec uses a verb
this recorder doesn't know).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ActionResult:
    """The outcome of executing one declarative ``Action``.

    Returned by ``execute_action`` (was ``None`` before). Consumed by
    :class:`RunReport` for telemetry, and by the orchestrator's
    ``after_action`` hook for custom downstream handling.
    """

    kind: str
    """The action verb that ran (``click``, ``fill``, ``select``, …)."""

    ok: bool
    """``True`` if the action succeeded; ``False`` if it was a no-op or errored."""

    target: str | None = None
    value: str | None = None
    note: str | None = None
    elapsed_ms: int = 0

    error_kind: str | None = None
    """One of: ``target_not_found``, ``timeout``, ``unknown_kind``, ``playwright``, ``other``. ``None`` on success."""

    error_message: str | None = None
    """Free-form message for logs; not parsed by anything machine-readable."""

    scene_index: int | None = None
    """1-based original spec index of the scene this action belongs to.

    Stamped by the orchestrator (``Recorder.run_scene``) so downstream tooling
    can group action results by scene without re-parsing the spec. ``None``
    means the action was executed outside any scene loop (e.g. a direct
    ``execute_action`` test call).
    """


@dataclass
class RunReport:
    """All :class:`ActionResult` records from a recorder run, plus summary helpers.

    The orchestrator owns one of these for the lifetime of a recording and
    prints its summary at the end. Downstream tools (canopy:walkthrough eval)
    can also read :meth:`as_dict` for grading.
    """

    results: list[ActionResult] = field(default_factory=list)

    def record(self, r: ActionResult) -> None:
        """Append one result. Called by ``execute_action`` after each action."""
        self.results.append(r)

    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.ok)

    def fail_count(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    def failures(self) -> list[ActionResult]:
        return [r for r in self.results if not r.ok]

    def summary(self) -> str:
        """One-line summary like ``"28 actions: 23 ok, 5 failed"``."""
        n = len(self.results)
        ok = self.ok_count()
        bad = n - ok
        if not n:
            return "0 actions"
        if not bad:
            return f"{n} actions: all ok"
        return f"{n} actions: {ok} ok, {bad} failed"

    def as_dict(self) -> dict:
        return {
            "total": len(self.results),
            "ok": self.ok_count(),
            "failed": self.fail_count(),
            "actions": [asdict(r) for r in self.results],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent)


class ActionAssertError(RuntimeError):
    """Raised by ``execute_action`` when ``must_succeed=true`` on a failing action.

    Lets a spec opt into fail-loud behavior on a per-action basis — for the
    critical "without this, the rest of the scene is gibberish" steps —
    while keeping the default behavior of "log + continue, one bad step
    must not kill the render".
    """
