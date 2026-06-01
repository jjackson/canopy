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
"""

from __future__ import annotations

import time
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
    ) -> None:
        self.config = config or RecorderConfig()
        self.base_url = (base_url or "").rstrip("/")
        self.report = report or RunReport()

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

    # ---- implementation -------------------------------------------------

    def goto_and_settle(self, page: Page, url: str) -> None:
        """Navigate without depending on ``networkidle``.

        ``networkidle`` hangs on apps with long-poll or streaming endpoints
        (labs uses both). ``domcontentloaded`` + a brief settle is enough for
        recording — the page is *visible*, not necessarily *idle*.
        """
        page.goto(url, wait_until="domcontentloaded", timeout=self.config.goto_timeout_ms)
        try:
            page.wait_for_load_state("load", timeout=self.config.load_settle_timeout_ms)
        except Exception:
            pass
        page.wait_for_timeout(self.config.goto_settle_ms)

    def run_scene(self, page: Page, scene: dict) -> float:
        """Record one scene. Returns elapsed seconds (floored by ``min_hold_ms``).

        Order: hook ``before_scene`` → resolve nav target → maybe navigate →
        ``initial_hold_ms`` → each action with ``before_action`` / ``after_action``
        → ``final_hold_ms`` → hook ``after_scene``.
        """
        url = self.goto_for_scene(scene, page.url)
        if url is not None:
            print(f"  · goto {url}")
            self.goto_and_settle(page, url)
        else:
            print(f"  · staying on {page.url}  — no nav for this scene")

        self.before_scene(scene)
        page.wait_for_timeout(self.config.initial_hold_ms)

        start = time.monotonic()
        scene_results: list[ActionResult] = []
        for action in (scene.get("actions") or []):
            self.before_action(scene, action)
            result = execute_action(page, action, base_url=self.base_url, config=self.config)
            self.report.record(result)
            scene_results.append(result)
            self.after_action(scene, action, result)

        page.wait_for_timeout(self.config.final_hold_ms)
        self.after_scene(scene, scene_results)

        elapsed_s = time.monotonic() - start + (self.config.initial_hold_ms + self.config.final_hold_ms) / 1000
        return max(elapsed_s, self.config.min_hold_ms / 1000)

    def run(self, page: Page, scenes: list[dict]) -> float:
        """Record every scene in ``scenes``. Returns total elapsed seconds."""
        total = 0.0
        n = len(scenes)
        for i, scene in enumerate(scenes, 1):
            title = scene.get("title", f"(scene {i})")
            print(f"\n=== Scene {i}/{n}: {title}")
            total += self.run_scene(page, scene)
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
