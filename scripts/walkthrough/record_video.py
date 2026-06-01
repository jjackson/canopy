#!/usr/bin/env python3
"""
record_video.py — Silent video recording for canopy:walkthrough specs.

Reads the spec YAML and replays each scene's URL + actions through a Playwright
Chromium context with ``record_video`` enabled, then converts the resulting
webm to mp4 via ffmpeg. Produces one silent mp4 alongside the HTML deck.

The recording loop lives in :class:`walkthrough._lib.orchestrator.Recorder` —
this script is a thin CLI over it. To customise behaviour (skip nav when the
URL hasn't changed, alternate viewport, custom hooks), subclass ``Recorder``
in a one-off script and call ``.run(page, scenes)``; no need to fork this CLI.

Usage:
    python3 record_video.py \\
        --spec docs/walkthroughs/<name>.yaml \\
        --output screenshots/walkthroughs/<name>.mp4 \\
        [--cookies /tmp/walkthrough-cookies.json] \\
        [--input /tmp/walkthrough-run-data.json] \\
        [--scene 2,4 | --scene 2-4 | --scene name-match] \\
        [--skip-same-url] \\
        [--report run-report.json] \\
        [--snapshots screenshots/walkthroughs/<name>/] \\
        [--snapshot-empty-scenes]

``--spec`` is the source of truth for scenes. ``--input`` is accepted for
backward compatibility: a walkthrough-run-data.json from canopy:walkthrough
narrows the spec's scenes to the ones that were actually captured (so a
``--scene 3`` partial run records exactly that scene). When ``--input`` is
absent the full spec is recorded.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("ERROR: pyyaml not installed. Run: pip install pyyaml")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit(
        "ERROR: playwright not installed.\n"
        "  pip install 'playwright>=1.40' && python -m playwright install chromium\n"
        "  (or install canopy's optional browser deps: pip install -e '<canopy>[browser]')"
    )

# Recorder lib lives next to this script in _lib/. Add this script's dir to the
# path so `python3 record_video.py` (invoked by path) can import it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib.config import RecorderConfig  # noqa: E402
from _lib.orchestrator import Recorder, SkipSameUrlRecorder  # noqa: E402
from _lib.recorder import CURSOR_OVERLAY_JS  # noqa: E402


# --------------------------------------------------------------------------- #
# helpers


def check_ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if not p:
        sys.exit("ERROR: ffmpeg not found on PATH. Install: brew install ffmpeg")
    return p


def webm_to_mp4(ffmpeg: str, webm: Path, out: Path) -> None:
    """Re-encode the Playwright-recorded webm to a faststart mp4 via ffmpeg."""
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Converting {webm.name} → {out.name}")
    result = subprocess.run(
        [
            ffmpeg, "-y", "-i", str(webm),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-preset", "fast", "-crf", "23",
            str(out),
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        sys.exit(f"ERROR: ffmpeg failed (exit {result.returncode}):\n{result.stderr[-2000:]}")


def _is_empty_scene(scene: dict) -> bool:
    """A scene with no ``actions`` is a narrative-only beat.

    Used by ``--skip-empty-scenes`` to drop those from the recording loop —
    the deck still shows them as title-card slides built from spec.scenes
    independently, so the narrative survives. Same gate as
    ``Recorder.take_snapshot``'s ``has_actions`` check (kept here as a
    separate helper so the filter in ``main`` and any future caller share
    one definition of "empty")."""
    return not bool(scene.get("actions") or [])


def filter_empty_scenes(scenes: list[dict]) -> list[dict]:
    """Drop scenes whose ``actions`` list is empty, preserving order and
    each surviving scene's 1-based ORIGINAL spec ``scene_index``.

    Pure function, no I/O — exercised by unit tests without spinning a
    browser. ``record_video.main`` calls this when ``--skip-empty-scenes``
    is set."""
    return [s for s in scenes if not _is_empty_scene(s)]


def build_scenes_from_spec(spec: dict, base_url: str, *, run_data: dict | None) -> list[dict]:
    """Resolve spec.scenes to the scene records the Recorder consumes.

    Each scene is ``{"url": str | None, "title": str, "actions": [...]}``.
    The URL comes from one of (in priority order):
      1. An explicit ``url:`` on the scene (the cleanest authoring path).
      2. The first ``goto`` action's target — the scene's own canonical start.
      3. The matching slide in ``run_data`` (legacy capture path).
      4. ``None`` — the orchestrator stays on the previous scene's ending page.

    The ``None`` default matters: a multi-scene narrative often runs like
    "scene 2 clicks a button that navigates, and scene 3 continues from
    there". Forcing a nav to ``base/`` for those scenes would wipe the JS
    state scene 2 just built. Authors who want a hard reset use
    ``url: /...`` (or a ``goto`` action) explicitly.

    If ``run_data`` is provided, only scenes with a matching captured slide
    are returned — so ``--scene 3`` upstream is honoured here. Without
    ``run_data`` we record every scene in the spec.
    """
    spec_scenes = spec.get("scenes") or []
    base = base_url.rstrip("/")

    # Build a 1-based index → captured URL map from run_data (if present).
    captured_urls: dict[int, str] = {}
    captured_filter: list[int] | None = None
    if run_data is not None:
        captured_filter = []
        for slide in run_data.get("slides", []):
            if slide.get("type") != "scene":
                continue
            idx = slide.get("scene_index")
            if idx is None:
                continue
            captured_filter.append(int(idx))
            if slide.get("url"):
                captured_urls[int(idx)] = slide["url"]

    def _absolutize(u: str) -> str:
        u = (u or "").strip()
        if not u:
            return ""
        return u if u.startswith("http") else base + u

    scenes: list[dict] = []
    for i, s in enumerate(spec_scenes, 1):
        if captured_filter is not None and i not in captured_filter:
            continue

        actions = list(s.get("actions") or [])
        url: str | None = None
        explicit = s.get("url")
        if explicit:
            url = _absolutize(explicit)
        if not url:
            first_goto = next((a for a in actions if (a.get("kind") or "") == "goto"), None)
            if first_goto:
                url = _absolutize(first_goto.get("target") or first_goto.get("value") or "")
        if not url:
            url = captured_urls.get(i)

        scenes.append({
            "url": url,  # may be None → orchestrator stays on previous URL
            "title": s.get("title", f"Scene {i}"),
            "video_hold_seconds": s.get("video_hold_seconds"),
            "actions": actions,
            # 1-based ORIGINAL spec index — preserved even when ``--input`` /
            # ``--scene`` filters narrow the list (so ``scene_index=3`` on a
            # partial run still means "spec scene 3", not "third in the
            # filtered list"). Snapshots and ActionResult.scene_index both
            # consume this.
            "scene_index": i,
        })
    return scenes


# --------------------------------------------------------------------------- #
# main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="walkthrough YAML spec (source of truth for scenes)")
    ap.add_argument("--output", required=True, help="output mp4 path")
    ap.add_argument("--input", help="walkthrough run JSON (optional — narrows scenes to captured set)")
    ap.add_argument("--cookies", help="optional cookies JSON exported by `browse cookies`")
    ap.add_argument(
        "--skip-same-url",
        action="store_true",
        help="don't re-navigate between scenes whose URL hasn't changed (preserves JS state)",
    )
    ap.add_argument(
        "--report",
        help="optional path to write the JSON RunReport (per-action results + summary)",
    )
    ap.add_argument(
        "--snapshots",
        help=(
            "optional dir for per-scene screenshots + page-text JSON "
            "(scene_<N>.png + scene_<N>_page_text.json — captured at each "
            "scene's steady state). Used by canopy:walkthrough eval + DDD "
            "concept judges."
        ),
    )
    ap.add_argument(
        "--snapshot-empty-scenes",
        action="store_true",
        help=(
            "snapshot scenes with no actions too (default: skip — they would "
            "duplicate the previous scene's steady-state frame)."
        ),
    )
    ap.add_argument(
        "--skip-empty-scenes",
        action="store_true",
        help=(
            "don't record scenes whose actions list is empty (the narrative-"
            "only back half of long specs). The mp4 then skips those scenes "
            "entirely — the deck still shows them as title-card slides built "
            "from spec.scenes independently, so the narrative survives. "
            "Default: record every scene (back-compat)."
        ),
    )
    args = ap.parse_args()

    ffmpeg = check_ffmpeg()
    spec = yaml.safe_load(Path(args.spec).read_text())
    run_data: dict | None = None
    if args.input:
        run_data = json.loads(Path(args.input).read_text())

    # Build the RecorderConfig: pace preset, optional spec override.
    pace = spec.get("video_pace", "fast")
    if pace not in ("fast", "medium", "slow"):
        sys.exit(f"ERROR: video_pace must be fast | medium | slow (got: {pace!r})")
    config = RecorderConfig.for_pace(pace).with_overrides(spec.get("video_recorder_config") or {})

    viewport_w = int(spec.get("video_viewport_width", 1280))
    viewport_h = int(spec.get("video_viewport_height", 720))
    base_url = (spec.get("base_url") or "").rstrip("/")

    scenes = build_scenes_from_spec(spec, base_url, run_data=run_data)
    if args.skip_empty_scenes:
        # Drop scenes with no actions from the recording loop entirely. The
        # deck is built from spec.scenes separately (generate_presentation),
        # so narrative-only beats still appear as title-card slides — we just
        # don't waste 4-6s of clip on a static page that holds min_hold_ms
        # on whatever the previous scene's last URL was. Filter AFTER
        # build_scenes_from_spec so the surviving scenes keep their 1-based
        # ORIGINAL spec scene_index (matches snapshot + ActionResult tagging).
        before = len(scenes)
        scenes = filter_empty_scenes(scenes)
        skipped = before - len(scenes)
        if skipped:
            print(f"  · --skip-empty-scenes: dropped {skipped} action-empty scene(s) from the recording")
    if not scenes:
        sys.exit("ERROR: no scenes resolved from spec (check --input filtering)")

    print(f"Recording {len(scenes)} scenes at pace={pace} ({viewport_w}x{viewport_h})")

    with tempfile.TemporaryDirectory(prefix="walkthrough-video-") as td:
        video_dir = Path(td)
        with sync_playwright() as p:
            # SwiftShader so headless Chromium can render WebGL — Mapbox GL,
            # three.js, deck.gl all fail to initialize without a GPU otherwise,
            # leaving a blank canvas the cursor clicks into (a map `draw` then
            # places no vertices). SwiftShader is Chromium's CPU GL backend; the
            # explicit flag is required since Chrome dropped the auto-fallback.
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--enable-unsafe-swiftshader",
                    "--use-angle=swiftshader",
                    "--ignore-gpu-blocklist",
                ],
            )
            context = browser.new_context(
                viewport={"width": viewport_w, "height": viewport_h},
                record_video_dir=str(video_dir),
                record_video_size={"width": viewport_w, "height": viewport_h},
            )
            # Synthetic cursor + click ripple (headless Chromium draws no OS
            # cursor). add_init_script runs at document-create on every nav, so
            # the cursor survives the per-scene page changes.
            context.add_init_script(CURSOR_OVERLAY_JS)
            # Auto-accept window.confirm/alert dialogs (e.g. destructive
            # "regenerate?" prompts) so a scripted click doesn't hang the render.
            context.on("dialog", lambda d: d.accept())

            if args.cookies:
                cookies = json.loads(Path(args.cookies).read_text())
                if cookies:
                    context.add_cookies(cookies)

            page = context.new_page()

            # URL-based auth (e.g. /auth/e2e-login?token=...) for specs that
            # use a magic-link login instead of cookie import.
            if not args.cookies:
                auth = spec.get("auth") or {}
                if auth.get("type") == "url" and auth.get("url"):
                    try:
                        page.goto(base_url + auth["url"], wait_until="networkidle", timeout=30000)
                    except Exception as e:
                        print(f"  ! auth nav warning: {e}", file=sys.stderr)

            recorder_cls = SkipSameUrlRecorder if args.skip_same_url else Recorder
            recorder = recorder_cls(
                config=config,
                base_url=base_url,
                snapshot_dir=Path(args.snapshots) if args.snapshots else None,
                snapshot_empty_scenes=bool(args.snapshot_empty_scenes),
            )
            total_seconds = recorder.run(page, scenes)

            context.close()  # flush video
            browser.close()

            recorder.print_summary()
            if args.report:
                Path(args.report).parent.mkdir(parents=True, exist_ok=True)
                Path(args.report).write_text(recorder.report.to_json())
                print(f"Wrote report: {args.report}")

        webms = list(video_dir.glob("*.webm"))
        if not webms:
            sys.exit("ERROR: no video file produced by Playwright")
        out_path = Path(args.output)
        webm_to_mp4(ffmpeg, webms[0], out_path)
        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"✓ {out_path} ({size_mb:.1f} MB, ~{total_seconds:.0f}s of footage)")


if __name__ == "__main__":
    main()
