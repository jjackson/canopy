"""High-level recording orchestrator with overridable hooks.

Before this module the per-scene recording loop lived inside
``record_video.main()`` — one 116-line function that opened the browser, loaded
cookies, iterated scenes, and shelled out to ffmpeg. To change the per-scene
nav strategy (e.g. "skip nav when the URL hasn't changed, to preserve JS state
between scenes") you had to fork the entire orchestrator. The
``microplans-10-wards`` recording needed exactly that change and ended up
hand-written into a one-off script.

Now :class:`Recorder` owns the per-scene + per-action loop with five hooks:

- :meth:`Recorder.goto_for_scene` — decide where to navigate (or whether to stay)
- :meth:`Recorder.before_scene` / :meth:`Recorder.after_scene` — bracket a scene
- :meth:`Recorder.before_action` / :meth:`Recorder.after_action` — bracket an action

Override any subset to customise. ``record_video.py`` instantiates a base
:class:`Recorder`; specialised scripts subclass for behaviour like skip-nav
(see :class:`SkipSameUrlRecorder`) without re-implementing the loop.

The orchestrator does NOT own the browser lifecycle — that's the CLI's job. A
:class:`Recorder` takes a Playwright :class:`Page` in :meth:`run` and writes to
its :class:`RunReport`. Easy to drive from a test that hands in a mocked Page.

**Per-scene snapshots.** Pass ``snapshot_dir=Path(...)`` to capture a steady-state
PNG + ``document.body.innerText`` JSON per scene. The capture moment is between
the action loop and the scene's ``final_hold_ms`` — after all scripted actions
have run and the post-action settle has fired, before the next scene navigates.
That's the same frame the deck's screenshot strip lifts; downstream judges
(``canopy:walkthrough`` eval, ``ddd-concept-eval``) read these files directly
instead of re-driving the page. Action-empty scenes (the narrative-only back-
half of a long spec) are skipped by default — they have nothing the cursor
could change between init and final, so the snapshot would just duplicate the
previous scene's. Pass ``snapshot_empty_scenes=True`` to override.
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

from .config import RecorderConfig
from .recorder import execute_action
from .results import ActionResult, RunReport


class Recorder:
    """Run a sequence of scenes against a Playwright Page.

    Subclass to customise navigation, scene/action bracketing, or how scenes
    are loaded. The default behaviour matches the pre-refactor ``record_video``
    loop: each scene navigates to its ``url`` (overwriting any prior page state),
    then runs its ``actions`` list, then holds for ``final_hold_ms``.
    """

    def __init__(
        self,
        *,
        config: RecorderConfig | None = None,
        base_url: str = "",
        report: RunReport | None = None,
        snapshot_dir: Path | None = None,
        snapshot_empty_scenes: bool = False,
    ) -> None:
        self.config = config or RecorderConfig()
        self.base_url = (base_url or "").rstrip("/")
        self.report = report or RunReport()
        # When set, ``take_snapshot`` fires at each scene's steady state and
        # writes ``scene_<N>.png`` + ``scene_<N>_page_text.json``. The directory
        # is created lazily on the first snapshot.
        self.snapshot_dir: Path | None = Path(snapshot_dir) if snapshot_dir else None
        self.snapshot_empty_scenes = snapshot_empty_scenes
        # Records the indices snapshotted, in order. Useful in tests +
        # downstream tooling that wants to enumerate captured scenes without
        # rescanning the directory.
        self.snapshots_taken: list[int] = []

    # ---- hooks (override these) -----------------------------------------

    def goto_for_scene(self, scene: dict, current_url: str | None) -> str | None:
        """Return the absolute URL to navigate to, or ``None`` to stay put.

        Default: always navigate to the scene's ``url`` if it has one.
        Subclasses override to add "skip nav when URL hasn't changed" or
        "never nav, the previous scene's actions already moved us".
        """
        url = scene.get("url")
        if not url:
            return None
        return url if url.startswith("http") else self.base_url + url

    def before_scene(self, scene: dict) -> None:
        """Hook fired before a scene starts (after any nav settle)."""

    def after_scene(self, scene: dict, scene_results: list[ActionResult]) -> None:
        """Hook fired after a scene's actions finish."""

    def before_action(self, scene: dict, action: dict) -> None:
        """Hook fired before each action runs."""

    def after_action(self, scene: dict, action: dict, result: ActionResult) -> None:
        """Hook fired after each action runs (success or failure)."""

    def take_snapshot(self, page: Page, scene: dict, scene_index: int) -> None:
        """Capture a per-scene PNG + page-text JSON at this scene's steady state.

        Called between the action loop and ``final_hold_ms`` — after the last
        action's ``post_*_settle`` has fired, before the next scene navigates
        away. Action-empty scenes (the narrative-only back half of a long
        spec) are skipped unless ``snapshot_empty_scenes=True`` — there's
        nothing to capture between init and final that a previous-scene
        snapshot didn't already record.

        Files are named ``scene_<scene_index>.png`` and
        ``scene_<scene_index>_page_text.json`` so a ``--scene 3`` partial run
        produces ``scene_3.*``, not ``scene_1.*`` — matches the deck +
        actionability eval indexing.

        Overridable: subclasses can switch to viewport-only screenshots,
        write to S3, or grab additional artifacts (network HAR, ARIA tree)
        without re-implementing the steady-state gating.
        """
        if self.snapshot_dir is None:
            return
        has_actions = bool(scene.get("actions") or [])
        if not has_actions and not self.snapshot_empty_scenes:
            return
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        png_path = self.snapshot_dir / f"scene_{scene_index}.png"
        text_path = self.snapshot_dir / f"scene_{scene_index}_page_text.json"
        try:
            page.screenshot(path=str(png_path), full_page=True)
        except Exception as e:  # noqa: BLE001 — never let a snapshot kill the run
            print(f"  ! snapshot screenshot failed for scene {scene_index}: {e}")
            return
        try:
            inner_text = page.evaluate("() => document.body && document.body.innerText || ''")
        except Exception as e:  # noqa: BLE001
            print(f"  ! snapshot page-text failed for scene {scene_index}: {e}")
            inner_text = ""
        payload = {
            "scene_index": scene_index,
            "url": getattr(page, "url", "") or "",
            "title": scene.get("title", f"Scene {scene_index}"),
            "page_text": inner_text,
        }
        text_path.write_text(json.dumps(payload, indent=2))
        self.snapshots_taken.append(scene_index)
        print(f"  · snapshot scene_{scene_index}.png + scene_{scene_index}_page_text.json")

    # ---- implementation -------------------------------------------------

    def goto_and_settle(self, page: Page, url: str, *, skip_settle: bool = False) -> None:
        """Navigate without depending on ``networkidle``.

        ``networkidle`` hangs on apps with long-poll or streaming endpoints
        (labs uses both). ``domcontentloaded`` + a brief settle is enough for
        recording — the page is *visible*, not necessarily *idle*.

        ``skip_settle=True`` omits the ``goto_settle_ms`` blind pause at the
        end. ``run_scene`` passes True when the first action is ``wait_for``
        — the wait_for IS the settle (it polls until the page state is
        right), so the extra 1200ms of blind hold is pure dead air on top.
        Backward-compatible default (False) keeps the original behavior for
        any external caller.
        """
        page.goto(url, wait_until="domcontentloaded", timeout=self.config.goto_timeout_ms)
        try:
            page.wait_for_load_state("load", timeout=self.config.load_settle_timeout_ms)
        except Exception:
            pass
        if not skip_settle:
            page.wait_for_timeout(self.config.goto_settle_ms)

    def run_scene(self, page: Page, scene: dict, *, scene_index: int | None = None) -> float:
        """Record one scene. Returns elapsed seconds (floored by ``min_hold_ms``).

        Order: hook ``before_scene`` → resolve nav target → maybe navigate →
        ``initial_hold_ms`` → each action with ``before_action`` / ``after_action``
        → ``final_hold_ms`` → hook ``after_scene``.

        ``scene_index`` is the 1-based ORIGINAL spec index of this scene (the
        ``--scene 3`` partial-run case still gets ``scene_index=3``, not
        ``scene_index=1``). It's stamped onto each ``ActionResult`` so a
        downstream grader can group results by scene without re-parsing the
        spec. Prefers an explicit kwarg; otherwise falls back to
        ``scene["scene_index"]`` (set by ``build_scenes_from_spec``).
        """
        idx = scene_index if scene_index is not None else scene.get("scene_index")
        url = self.goto_for_scene(scene, page.url)
        # Inspect the first action ONCE: a leading ``wait_for`` is itself a
        # settle (it polls until a known page state appears), so the
        # ``goto_settle_ms`` blind hold AND the ``initial_hold_ms`` blind
        # hold both become pure dead air on top of it. Skip both in that
        # case. For every other first-action kind (click, scroll_to, fill,
        # etc.) the original behavior holds — the holds give the page a
        # moment to render before the cursor moves.
        actions_list = scene.get("actions") or []
        first_action_kind = (
            (actions_list[0].get("kind") or "") if actions_list and isinstance(actions_list[0], dict) else ""
        )
        leading_waitfor = first_action_kind == "wait_for"

        if url is not None:
            print(f"  · goto {url}")
            if leading_waitfor:
                print("  · deferring goto_settle_ms (first action is wait_for)")
            self.goto_and_settle(page, url, skip_settle=leading_waitfor)
        else:
            print(f"  · staying on {page.url}  — no nav for this scene")

        self.before_scene(scene)
        if leading_waitfor:
            # Skip initial_hold_ms — the wait_for that's about to run is the
            # settle. Print once per scene so authors can SEE the recorder is
            # using the cheap path and not "doing nothing".
            print("  · deferring initial_hold_ms (first action is wait_for)")
        else:
            page.wait_for_timeout(self.config.initial_hold_ms)

        start = time.monotonic()
        scene_results: list[ActionResult] = []
        for action in (scene.get("actions") or []):
            self.before_action(scene, action)
            result = execute_action(page, action, base_url=self.base_url, config=self.config)
            # Stamp the 1-based original spec scene index onto the result. We
            # ``dataclasses.replace`` because ActionResult is frozen — keeps
            # ``execute_action`` scene-agnostic (it doesn't know or care which
            # scene it's serving) while preserving "all results carry their
            # scene" for the run report.
            if idx is not None:
                result = dataclasses.replace(result, scene_index=int(idx))
            self.report.record(result)
            scene_results.append(result)
            self.after_action(scene, action, result)

        # Steady-state moment: actions are done, their post-action settle has
        # fired, and we're about to hold + transition. This is the same frame
        # the deck's screenshot strip lifts; capture it here so downstream
        # judges read the same surface a viewer sees.
        if idx is not None:
            self.take_snapshot(page, scene, int(idx))

        page.wait_for_timeout(self.config.final_hold_ms)
        self.after_scene(scene, scene_results)

        elapsed_s = time.monotonic() - start + (self.config.initial_hold_ms + self.config.final_hold_ms) / 1000
        return max(elapsed_s, self.config.min_hold_ms / 1000)

    def run(self, page: Page, scenes: list[dict]) -> float:
        """Record every scene in ``scenes``. Returns total elapsed seconds.

        Each scene's ``scene_index`` (set by ``build_scenes_from_spec`` to the
        1-based ORIGINAL spec index) is threaded into ``run_scene`` so action
        results get stamped with the right index even on partial (``--scene 3``)
        runs. Scenes without ``scene_index`` fall back to the loop's 1-based
        position — fine for ad-hoc test callers that hand in raw scene dicts.
        """
        total = 0.0
        n = len(scenes)
        for i, scene in enumerate(scenes, 1):
            title = scene.get("title", f"(scene {i})")
            print(f"\n=== Scene {i}/{n}: {title}")
            total += self.run_scene(page, scene, scene_index=scene.get("scene_index", i))
        return total

    def print_summary(self) -> None:
        """Print the run's :class:`RunReport` summary + every failure with its tag."""
        print(f"\nRun report: {self.report.summary()}")
        failures = self.report.failures()
        if failures:
            print("Failures:")
            for r in failures:
                target_repr = f" target={r.target!r}" if r.target else ""
                value_repr = f" value={r.value!r}" if r.value else ""
                print(f"  - {r.kind}({r.error_kind}){target_repr}{value_repr}: {r.error_message or ''}")


class SkipSameUrlRecorder(Recorder):
    """Recorder that preserves JS state between scenes that share a URL.

    Default ``Recorder.goto_for_scene`` re-navigates on every scene, which
    wipes any JS state the previous scene's actions built up (the resolved
    bulk-create table, the picked sidebar checkboxes, an open modal). For
    flows where one scene's outcome IS the next scene's starting state, use
    this subclass — it skips the nav when the requested URL matches what the
    page is already showing.
    """

    def goto_for_scene(self, scene: dict, current_url: str | None) -> str | None:
        url = super().goto_for_scene(scene, current_url)
        if url is None or current_url is None:
            return url
        if _normalize_url(current_url) == _normalize_url(url):
            return None
        return url


def _normalize_url(u: str) -> str:
    """Compare-friendly URL: strip trailing slash and fragment."""
    return (u or "").split("#")[0].rstrip("/")


# Re-export the action-driver entry point so callers can ``from
# walkthrough._lib.orchestrator import execute_action`` without reaching into
# recorder.py. Keeps the orchestrator the obvious top-level surface.
__all__ = [
    "Recorder",
    "SkipSameUrlRecorder",
    "execute_action",
    "RecorderConfig",
    "RunReport",
    "ActionResult",
]
