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
PNG + ``document.body.innerText`` JSON per scene. The capture moment is after
the action loop AND the scene's ``final_hold_ms`` — all scripted actions have
run, the post-action settle and final hold have fired, and the next scene is
about to navigate; full-page captures scroll to top (and restore) so sticky
headers paint at the document top, with the bounce masked by the crossfade.
That's the same frame the deck's screenshot strip lifts; downstream judges
(``canopy:walkthrough`` eval, ``ddd-concept-eval``) read these files directly
instead of re-driving the page. Action-empty scenes (the narrative-only back-
half of a long spec) are skipped by default — they have nothing the cursor
could change between init and final, so the snapshot would just duplicate the
previous scene's. Pass ``snapshot_empty_scenes=True`` to override.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page

# A freeze-frame crossfade that hides the white flash a browser paints during
# navigation. We screenshot the outgoing scene, then on the incoming page lay
# that frame over the viewport at max z-index and fade it out once the new page
# is visually ready (its ``load`` event, or a safety cap). Without this, the
# continuous recording shows a jarring white blink between every scene.
_CROSSFADE_JS = r"""
(img) => {
  try {
    var o = document.createElement('div');
    o.setAttribute('data-wt-xfade', '1');
    o.style.cssText = 'position:fixed;inset:0;z-index:2147483647;pointer-events:none;'
      + 'opacity:1;transition:opacity 420ms ease;background:#ffffff center center / cover no-repeat';
    o.style.backgroundImage = 'url(' + img + ')';
    (document.body || document.documentElement).appendChild(o);
    var done = false;
    var fade = function () {
      if (done) return; done = true;
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          o.style.opacity = '0';
          setTimeout(function () { if (o && o.parentNode) o.parentNode.removeChild(o); }, 520);
        });
      });
    };
    // Fade once the incoming page is visually ready (a beat after load), or a
    // hard safety cap so the overlay can never get stuck covering the scene.
    if (document.readyState === 'complete') { setTimeout(fade, 200); }
    else { window.addEventListener('load', function () { setTimeout(fade, 140); }, { once: true }); }
    setTimeout(fade, 1700);
  } catch (e) {}
}
"""

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
        default_viewport: dict[str, int] | None = None,
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
        # Spec-level viewport — restored after any per-scene viewport override.
        # None → no restore (tests / callers that don't track viewport at all).
        self.default_viewport: dict[str, int] | None = (
            dict(default_viewport) if default_viewport else None
        )
        # Tracks the currently-applied viewport so we only call
        # ``page.set_viewport_size`` when it actually changes — avoids
        # gratuitous resize events on every scene.
        self._current_viewport: dict[str, int] | None = (
            dict(default_viewport) if default_viewport else None
        )
        # The recording timeline's zero point (time.monotonic()). The CLI sets
        # this right after ``context.new_page()`` — the moment Playwright's
        # video capture starts — so per-scene ``start_seconds`` offsets line up
        # with the produced mp4 (the webm is re-encoded 1:1). When unset (ad-hoc
        # callers / tests), it defaults lazily to the first scene's start, so
        # offsets are still internally consistent.
        self.recording_epoch: float | None = None

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

        Called after the action loop and ``final_hold_ms`` — the last
        action's ``post_*_settle`` and the final hold have fired, and the next
        scene is about to navigate away. Action-empty scenes (the narrative-only back half of a long
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
        # Per-scene capture mode. Default is a full-page screenshot. Scenes whose
        # page is a tall TABLE + a map/chart (e.g. a plan-review page) set
        # ``full_page: false`` so the snapshot is just the viewport — the map/chart
        # is the hero instead of a sliver atop a 16,000px strip. A full-viewport
        # map page (e.g. the group overlay map) captures fine either way; this only
        # matters for table-dominant pages. WebGL/Mapbox itself renders + composites
        # correctly under the SwiftShader launch flags (see record_video.py) given a
        # long enough settle for tiles to paint — no special capture path needed.
        full_page = scene.get("full_page")
        full_page = True if full_page is None else bool(full_page)
        # Sticky-header artifact guard: Chromium's beyond-viewport capture
        # paints position:sticky/fixed elements at the LIVE scroll offset, so
        # a scene that ends scrolled down gets its navbar stamped mid-image
        # and a bar-less, clipped document top. Scroll to top for the capture
        # and restore after — capture runs post-final-hold, so the bounce sits
        # at the scene boundary under the crossfade. Viewport captures
        # (full_page: false) show the live viewport and need no correction.
        scroll_y = 0
        if full_page:
            try:
                scroll_y = int(page.evaluate("() => window.scrollY") or 0)
                if scroll_y:
                    page.evaluate("() => window.scrollTo(0, 0)")
                    page.wait_for_timeout(200)
            except Exception:  # noqa: BLE001 — capture correction is best-effort
                scroll_y = 0
        png_ok = self._screenshot_with_settle_retry(page, png_path, scene_index, full_page=full_page)
        if full_page and scroll_y:
            try:
                page.evaluate(f"() => window.scrollTo(0, {scroll_y})")
                page.wait_for_timeout(120)
            except Exception:  # noqa: BLE001
                pass
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
        # Always write the text dump so downstream judges have at least one
        # input per scene — even when the screenshot path failed (WebGL/Mapbox
        # pages hang ``Page.captureScreenshot`` in headless and the retry
        # exhausted). The text dump is what feeds visual-judge's anchor text;
        # losing the PNG degrades the eval but losing the text removes the
        # scene from the input entirely.
        text_path.write_text(json.dumps(payload, indent=2))
        if png_ok:
            self.snapshots_taken.append(scene_index)
            print(f"  · snapshot scene_{scene_index}.png + scene_{scene_index}_page_text.json")
        else:
            print(f"  · snapshot scene_{scene_index}_page_text.json (PNG failed after retry)")

    def _screenshot_with_settle_retry(
        self, page: Page, png_path: Path, scene_index: int, full_page: bool = True
    ) -> bool:
        """Take a full-page screenshot, settling and retrying once on timeout.

        WebGL / Mapbox / Canvas-heavy pages can hang ``Page.captureScreenshot``
        in headless Chromium — the recurring SwiftShader-headless bug. The DDD
        agent's manual workaround was to re-capture the failing scene in a
        separate ``playwright.sync_api`` session with an explicit 8-10s sleep
        before retrying ``page.screenshot()``. That's now built in.

        Strategy:
          1. Try ``page.screenshot(full_page=True, timeout=10s)``.
          2. On exception, settle 8s (give the WebGL canvas time to finish
             whatever frame it was mid-render on) and retry once with a 20s
             timeout.
          3. If the retry also fails, log a one-line warning and return False
             so the caller can still write the text dump (visual-judge anchor)
             and not silently lose the scene's input.

        One settle + one retry is enough — never retry forever.
        """
        try:
            page.screenshot(path=str(png_path), full_page=full_page, timeout=10000)
            return True
        except Exception as e:  # noqa: BLE001 — Playwright's TimeoutError isn't always exposed
            print(f"  ! scene {scene_index}: screenshot failed ({e}); settling 8s and retrying...")
        try:
            page.wait_for_timeout(8000)
        except Exception:  # noqa: BLE001 — even the settle is best-effort
            pass
        try:
            page.screenshot(path=str(png_path), full_page=full_page, timeout=20000)
            return True
        except Exception as e2:  # noqa: BLE001
            print(f"  ! scene {scene_index}: screenshot failed after retry: {e2}")
            return False

    # ---- implementation -------------------------------------------------

    def goto_and_settle(self, page: Page, url: str, *, skip_settle: bool = False) -> None:
        """Navigate without depending on ``networkidle``.

        ``networkidle`` hangs on apps with long-poll or streaming endpoints
        (labs uses both). ``domcontentloaded`` + a brief settle is enough for
        recording — the page is *visible*, not necessarily *idle*.

        ``skip_settle=True`` (caller knows the next action is ``wait_for``)
        uses the fastest possible navigation gate — ``wait_until="commit"``
        — and skips BOTH the ``load`` event wait AND the ``goto_settle_ms``
        blind hold. Rationale: after leaving a WebGL/Mapbox-heavy page, the
        torn-down GL context's residual telemetry and tile-fetch network
        activity can stall Playwright's lifecycle tracking; the ``load``
        event signal can hang for the full ``load_settle_timeout_ms``
        (8s default) while the viewport sits blank because Chromium hasn't
        painted the new page's first frame yet. The ``wait_for`` action
        that's about to fire will do its own polling for the target text /
        selector — much more accurate than guessing at ``load`` event
        timing.

        Backward-compatible default (``skip_settle=False``) keeps the
        original ``domcontentloaded`` + ``load`` + ``goto_settle_ms`` flow
        for any external caller and every non-``wait_for`` first action.
        """
        prev_frame = self._capture_frame(page)
        if skip_settle:
            # Fastest possible gate: return as soon as the navigation request
            # is committed. The wait_for action will poll until the target
            # appears — that's the real settle.
            print("  · using wait_until=commit (first action is wait_for; navigation gate deferred to it)")
            page.goto(url, wait_until="commit", timeout=self.config.goto_timeout_ms)
            self._crossfade(page, prev_frame)
            return
        page.goto(url, wait_until="domcontentloaded", timeout=self.config.goto_timeout_ms)
        self._crossfade(page, prev_frame)
        try:
            page.wait_for_load_state("load", timeout=self.config.load_settle_timeout_ms)
        except Exception:
            pass
        page.wait_for_timeout(self.config.goto_settle_ms)

    def _capture_frame(self, page: Page) -> str | None:
        """Grab the current viewport as a base64 PNG data URI for the crossfade.

        Returns ``None`` on the very first navigation (blank page — nothing to
        fade from) or if the screenshot fails (never block the nav on it).
        """
        if not getattr(self.config, "crossfade", True):
            return None
        try:
            if not page.url or page.url == "about:blank":
                return None
            png = page.screenshot(full_page=False, timeout=2500)
            return "data:image/png;base64," + base64.b64encode(png).decode("ascii")
        except Exception:
            return None

    def _crossfade(self, page: Page, prev_frame: str | None) -> None:
        """Lay the outgoing frame over the freshly-navigated page and fade it.

        Hides the browser's white navigation flash. Best-effort: the new
        document's execution context may briefly be unavailable right after
        ``commit`` — swallow and move on rather than fail the scene.
        """
        if not prev_frame:
            return
        try:
            page.evaluate(_CROSSFADE_JS, prev_frame)
        except Exception:
            pass

    def _apply_viewport(self, page: Page, viewport: dict[str, int] | None) -> None:
        """Resize the page viewport to ``viewport`` if different from current.

        Per-scene viewport override hook. The mp4's frame size is fixed at
        Playwright context creation (``record_video_size``); we cannot change
        that mid-stream. What we CAN change is the page's logical viewport —
        ``page.set_viewport_size`` adjusts the CSS pixel dimensions the page
        renders into, and the recording canvas re-fits / letterboxes the
        result into the fixed mp4 frame. A wider per-scene viewport gives the
        layout more horizontal room (a Mapbox + inspector panel scene that
        was crowded at 1280px gets the breathing room of 1440px) without
        bumping the whole spec's recording size.

        Skips the call when the requested viewport matches what's already
        applied (no-op fast path so unchanged scenes don't fire a gratuitous
        resize event mid-scene).
        """
        if viewport is None:
            # Restore-to-default path. If we don't know the default, do nothing.
            target = self.default_viewport
        else:
            target = {"width": int(viewport["width"]), "height": int(viewport["height"])}
        if target is None:
            return
        if self._current_viewport == target:
            return
        try:
            page.set_viewport_size(target)
        except Exception as e:  # noqa: BLE001 — never let a viewport tweak kill the run
            print(f"  ! viewport resize to {target} failed: {e}")
            return
        self._current_viewport = dict(target)
        if viewport is not None:
            print(f"  · viewport override → {target['width']}x{target['height']}")
        else:
            print(f"  · viewport restored → {target['width']}x{target['height']}")

    def run_scene(
        self,
        page: Page,
        scene: dict,
        *,
        scene_index: int | None = None,
        nav_sink: list[str] | None = None,
    ) -> float:
        """Record one scene. Returns elapsed seconds (floored by ``min_hold_ms``).

        Order: hook ``before_scene`` → resolve nav target → maybe navigate →
        ``initial_hold_ms`` → each action with ``before_action`` / ``after_action``
        → ``final_hold_ms`` → hook ``after_scene``.

        ``nav_sink`` is an optional shared list that the CLI wires to a Playwright
        ``framenavigated`` listener (main-frame URLs). Action-boundary ``page.url``
        snapshots miss client-side redirects that fire BETWEEN actions (e.g. an
        audit→workflow redirect that lands while the recorder is holding). We
        CLEAR the sink at scene start so it only carries this scene's
        navigations, then FOLD its contents into the scene's ``urls_visited`` at
        scene end. ``None`` (the default) is the no-sink path for ad-hoc callers.

        ``scene_index`` is the 1-based ORIGINAL spec index of this scene (the
        ``--scene 3`` partial-run case still gets ``scene_index=3``, not
        ``scene_index=1``). It's stamped onto each ``ActionResult`` so a
        downstream grader can group results by scene without re-parsing the
        spec. Prefers an explicit kwarg; otherwise falls back to
        ``scene["scene_index"]`` (set by ``build_scenes_from_spec``).
        """
        idx = scene_index if scene_index is not None else scene.get("scene_index")
        # Per-scene wall-clock timing for the run report. Captured BEFORE the
        # nav so ``start_seconds`` marks the moment this scene begins on the
        # recording timeline (nav + settle + actions + final hold all count
        # toward its duration). The epoch defaults to this scene's start when
        # the CLI didn't stamp one (ad-hoc callers).
        scene_start = time.monotonic()
        if self.recording_epoch is None:
            self.recording_epoch = scene_start
        # Clear the shared nav sink at the TRUE scene start (before the goto) so
        # it accumulates only THIS scene's main-frame navigations — including
        # the scene's own goto and any client-side redirect that fires while the
        # recorder holds. Folded into ``visited`` at scene end. The listener
        # that fills it is registered once on the page by the CLI.
        if nav_sink is not None:
            nav_sink.clear()
        # Per-scene viewport override: apply BEFORE the goto so the freshly-
        # loaded page lays out at the requested size from the first paint.
        # Restored AFTER final_hold_ms below (so the next scene starts at the
        # spec-level default).
        scene_viewport = scene.get("viewport")
        self._apply_viewport(page, scene_viewport)
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
        # initial_hold_ms is a post-nav settle: it gives the freshly-loaded
        # page a moment to paint before the cursor moves. Skip it when:
        #   (a) the first action is wait_for — the wait_for IS the settle, or
        #   (b) no navigation happened (url is None) — a stay-on-page scene
        #       has no page-load transition to settle for, and the PREVIOUS
        #       scene's final_hold_ms already provided any transition pause.
        # Otherwise keep the original behavior (back-compat for static-scene
        # paths and click-first scenes that need the page a moment to render).
        if leading_waitfor:
            print("  · deferring initial_hold_ms (first action is wait_for)")
        elif url is None:
            print("  · deferring initial_hold_ms (no nav for this scene)")
        else:
            page.wait_for_timeout(self.config.initial_hold_ms)

        start = time.monotonic()
        scene_results: list[ActionResult] = []
        # Collect the URLs this scene actually lands on, one ``page.url``
        # snapshot per action boundary. Seed with the post-nav URL (so a
        # nav-only scene still records where it went), then append after each
        # action (a click can trigger a redirect/SPA route change). Deduped +
        # order-preserved downstream in ``record_scene_urls``. Guarded because
        # ``page.url`` can raise on a torn-down page.
        visited: list[str] = []
        try:
            visited.append(page.url)
        except Exception:  # noqa: BLE001 — URL collection is best-effort telemetry
            pass
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
            try:
                visited.append(page.url)
            except Exception:  # noqa: BLE001 — best-effort telemetry
                pass
            self.after_action(scene, action, result)

        # End-of-scene hold. ``scene.video_hold_seconds`` (legacy per-scene
        # knob) overrides the global ``final_hold_ms`` for THIS scene only —
        # it dated from the scroll-pan-era recorder and had been a silent
        # no-op since the orchestrator refactor (passed through by
        # build_scenes_from_spec, consumed by nothing). Wiring it here gives
        # it one defined meaning in the timing model: the end-of-scene dwell.
        # For mid-scene cinematic dwells prefer explicit ``hold`` actions —
        # see the walkthrough SKILL's "Recording time & dead space" section.
        hold_override = scene.get("video_hold_seconds")
        final_hold_ms = (
            int(float(hold_override) * 1000) if hold_override else self.config.final_hold_ms
        )
        page.wait_for_timeout(final_hold_ms)

        # Steady-state moment: actions are done, their post-action settle and
        # final hold have fired, and we're about to transition. This is the
        # same frame the deck's screenshot strip lifts; capture it here —
        # AFTER the hold — so the full-page capture's scroll-to-top bounce
        # (see take_snapshot) lands at the scene cut, where the crossfade to
        # the next scene masks it, instead of mid-scene on film.
        if idx is not None:
            self.take_snapshot(page, scene, int(idx))

        self.after_scene(scene, scene_results)

        # Restore the spec-level viewport so the next scene starts at the
        # default. No-op when scene had no override or when
        # default_viewport is None (tests/callers that don't care).
        if scene_viewport is not None:
            self._apply_viewport(page, None)

        # Record this scene's slot on the recording timeline. Raw wall-clock
        # (nav included), unlike the floored return value below — the report
        # entry must match where the scene actually sits in the mp4.
        if idx is not None:
            self.report.record_scene_timing(
                scene_index=int(idx),
                title=scene.get("title", f"Scene {idx}"),
                start_seconds=scene_start - self.recording_epoch,
                duration_seconds=time.monotonic() - scene_start,
            )
            # Fold the framenavigated sink (client-side redirects) in AFTER the
            # action-boundary snapshots, then record. ``record_scene_urls``
            # dedupes order-preserving, so a URL already captured at an action
            # boundary won't double up.
            if nav_sink is not None:
                visited = visited + list(nav_sink)
            self.report.record_scene_urls(scene_index=int(idx), urls=visited)

        elapsed_s = time.monotonic() - start + (self.config.initial_hold_ms + final_hold_ms) / 1000
        return max(elapsed_s, self.config.min_hold_ms / 1000)

    def run(self, page: Page, scenes: list[dict], *, nav_sink: list[str] | None = None) -> float:
        """Record every scene in ``scenes``. Returns total elapsed seconds.

        Each scene's ``scene_index`` (set by ``build_scenes_from_spec`` to the
        1-based ORIGINAL spec index) is threaded into ``run_scene`` so action
        results get stamped with the right index even on partial (``--scene 3``)
        runs. Scenes without ``scene_index`` fall back to the loop's 1-based
        position — fine for ad-hoc test callers that hand in raw scene dicts.

        ``nav_sink`` (when supplied) is the shared ``framenavigated`` list,
        passed through to each :meth:`run_scene` so client-side redirects fold
        into the right scene's ``urls_visited``.
        """
        total = 0.0
        n = len(scenes)
        for i, scene in enumerate(scenes, 1):
            title = scene.get("title", f"(scene {i})")
            print(f"\n=== Scene {i}/{n}: {title}")
            total += self.run_scene(
                page, scene, scene_index=scene.get("scene_index", i), nav_sink=nav_sink
            )
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
