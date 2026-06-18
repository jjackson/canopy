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

    scenes: list[dict] = field(default_factory=list)
    """Per-scene timing entries, in recording order. INVARIANT: ``_scene_timing_index``
    mirrors these SAME dict objects by identity, so any new code that appends a
    scene-timing entry MUST go through :meth:`record_scene_timing` (never
    ``self.scenes.append(...)`` directly) to keep the mirror in sync. Each entry::

        {"scene_index": int,        # 1-based ORIGINAL spec index
         "title": str,
         "start_seconds": float,    # offset into the recording timeline
         "duration_seconds": float}

    ``start_seconds`` is measured from the recorder's ``recording_epoch``
    (set by ``record_video.main`` at page creation — the moment Playwright's
    webm starts; the final mp4 is that webm re-encoded, so offsets carry
    over). Scenes dropped by ``--skip-empty-scenes`` never run, so they get
    no entry. Downstream consumers (the DDD product-findings review) use
    these to deep-link a video at the scene a finding is about — see
    :func:`scene_timestamps`."""

    setup: dict | None = None
    """Data-setup provenance (the spec's ``setup:`` block execution record):
    command, cwd, rerun mode, skipped/skip_reason, exit code, duration, and
    the resolved ``${var}`` substitution variables. Stamped by
    ``record_video.main`` when the spec declares a setup block — the data a
    film was made on is part of the run's evidence chain. ``None`` for specs
    with no setup block (the key is then omitted from :meth:`as_dict`, so
    existing report consumers are unchanged)."""

    prewarm: dict | None = None
    """Pre-warm pass provenance: ``{"pages": int, "duration_seconds": float,
    "failures": [{"url": str, "error": str}, ...]}``. Stamped by
    ``record_video.main`` when the pre-warm pass ran (spec ``prewarm: true``
    or CLI ``--prewarm``). ``None`` when prewarm was off — the key is then
    omitted from :meth:`as_dict`, mirroring ``setup``."""

    _scene_timing_index: dict[int, dict] = field(default_factory=dict, repr=False)
    """``scene_index -> timing entry`` mirror of :attr:`scenes`, kept in sync by
    :meth:`record_scene_timing`. Lets :meth:`record_scene_urls` and
    :meth:`scene_timing_for` reach a scene's entry by index in O(1) without
    re-scanning the list. The mirrored dicts are the SAME objects stored in
    :attr:`scenes`, so mutations (adding ``urls_visited``) show up in both —
    and :meth:`as_dict`/`:meth:`to_json` serialize them correctly."""

    def record(self, r: ActionResult) -> None:
        """Append one result. Called by ``execute_action`` after each action."""
        self.results.append(r)

    def record_scene_timing(
        self,
        *,
        scene_index: int,
        title: str,
        start_seconds: float,
        duration_seconds: float,
    ) -> None:
        """Append one per-scene timing entry. Called by ``Recorder.run_scene``."""
        entry = {
            "scene_index": int(scene_index),
            "title": title,
            "start_seconds": round(float(start_seconds), 3),
            "duration_seconds": round(float(duration_seconds), 3),
        }
        self.scenes.append(entry)
        self._scene_timing_index[int(scene_index)] = entry

    def record_scene_urls(self, *, scene_index: int, urls: list[str]) -> None:
        """Record the URLs a scene navigated to, deduped + order-preserving.

        Stores them under ``urls_visited`` on the scene's timing entry (the
        same dict held in :attr:`scenes`, so it serializes via
        :meth:`as_dict`). Called by ``Recorder.run_scene`` with the list of
        ``page.url`` snapshots collected across the scene's actions. If no
        timing entry exists yet for ``scene_index`` (e.g. a test calls this
        before :meth:`record_scene_timing`), a bare entry is created so the
        URLs aren't dropped."""
        entry = self._scene_timing_index.get(int(scene_index))
        if entry is None:
            entry = {"scene_index": int(scene_index)}
            self.scenes.append(entry)
            self._scene_timing_index[int(scene_index)] = entry
        seen: set[str] = set()
        deduped: list[str] = []
        for u in urls or []:
            if u in seen:
                continue
            seen.add(u)
            deduped.append(u)
        entry["urls_visited"] = deduped

    def scene_timing_for(self, scene_index: int) -> dict:
        """Return the timing entry for ``scene_index`` (or ``{}`` if none)."""
        return self._scene_timing_index.get(int(scene_index), {})

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
        d = {
            "total": len(self.results),
            "ok": self.ok_count(),
            "failed": self.fail_count(),
            "actions": [asdict(r) for r in self.results],
            "scenes": list(self.scenes),
        }
        if self.setup is not None:
            d["setup"] = self.setup
        if self.prewarm is not None:
            d["prewarm"] = self.prewarm
        return d

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.as_dict(), indent=indent)


def scene_timestamps(report: dict) -> dict[int, float]:
    """Read ``scene_index -> start_seconds`` from a run-report dict.

    ``report`` is the parsed JSON written by ``record_video.py --report``
    (i.e. :meth:`RunReport.as_dict` output). Scenes that were skipped
    (``--skip-empty-scenes``) have no entry. Returns ``{}`` for reports
    written before per-scene timing existed — callers degrade to "no video
    deep-links" rather than crashing on old artifacts.

    Stdlib-only on purpose: ``scripts.ddd.findings_review`` imports this
    without dragging in Playwright (this module has no browser deps).
    """
    out: dict[int, float] = {}
    for entry in report.get("scenes") or []:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("scene_index")
        start = entry.get("start_seconds")
        if idx is None or start is None:
            continue
        try:
            out[int(idx)] = float(start)
        except (TypeError, ValueError):
            continue
    return out


class ActionAssertError(RuntimeError):
    """Raised by ``execute_action`` when ``must_succeed=true`` on a failing action.

    Lets a spec opt into fail-loud behavior on a per-action basis — for the
    critical "without this, the rest of the scene is gibberish" steps —
    while keeping the default behavior of "log + continue, one bad step
    must not kill the render".
    """
