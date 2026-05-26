#!/usr/bin/env python3
"""
record_video.py — Optional silent video recording for canopy:walkthrough.

Replays the scenes from a completed walkthrough run (using the URLs captured
in the run JSON) through a fresh Playwright Chromium context with
record_video enabled, then converts the resulting webm to mp4 via ffmpeg.

Runs AFTER the normal walkthrough capture/scoring flow — does not interfere
with screenshots, scores, or deck generation. Produces one silent mp4
alongside the HTML deck.

Pacing presets (fast / medium / slow) combine a short initial hold, a
smooth eased scroll over tall pages, and a short final hold. The scroll is
what keeps a "fast" walkthrough from feeling fast-forwarded — viewers
register motion as natural pace rather than a freeze-frame jump-cut.

Usage:
    python3 record_video.py \\
        --input /tmp/walkthrough-run-data.json \\
        --spec docs/walkthroughs/<name>.yaml \\
        --output screenshots/walkthroughs/<name>.mp4 \\
        [--cookies /tmp/walkthrough-cookies.json]
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Path to the cursor-overlay JS injected when `inject_cursor: true` is set
# on the walkthrough spec. Resolved relative to this script so the script
# stays portable when canopy is vendored or installed in different layouts.
_HERE = Path(__file__).resolve().parent
CURSOR_OVERLAY_JS = _HERE / "cursor_overlay.js"

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


# Pacing presets. Goal: a "fast" walkthrough that doesn't feel sped-up.
# initial_hold + (scroll_distance / scroll_speed) + final_hold, floored by min_hold.
PACING = {
    "fast":   {"initial_hold": 0.8, "scroll_speed": 1200, "final_hold": 0.5, "min_hold": 2.5},
    "medium": {"initial_hold": 1.5, "scroll_speed": 600,  "final_hold": 1.0, "min_hold": 4.0},
    "slow":   {"initial_hold": 2.5, "scroll_speed": 300,  "final_hold": 1.5, "min_hold": 6.0},
}


def check_ffmpeg() -> str:
    p = shutil.which("ffmpeg")
    if not p:
        sys.exit("ERROR: ffmpeg not found on PATH. Install: brew install ffmpeg")
    return p


def smooth_scroll(page, pace_config) -> float:
    """Scroll from top to bottom at pace_config['scroll_speed'] px/sec
    with ease-in-out cubic. Returns seconds spent scrolling."""
    height = page.evaluate("() => document.documentElement.scrollHeight")
    viewport_h = page.evaluate("() => window.innerHeight")
    distance = max(0, height - viewport_h)
    if distance < 50:
        return 0.0
    speed = pace_config["scroll_speed"]
    duration_ms = int((distance / speed) * 1000)
    page.evaluate(
        """([distance, duration]) => {
          return new Promise(resolve => {
            const start = performance.now();
            const startY = window.scrollY;
            function step(t) {
              const elapsed = t - start;
              const ratio = Math.min(1, elapsed / duration);
              const eased = ratio < 0.5
                ? 4 * ratio * ratio * ratio
                : 1 - Math.pow(-2 * ratio + 2, 3) / 2;
              window.scrollTo(0, startY + distance * eased);
              if (ratio < 1) requestAnimationFrame(step);
              else resolve();
            }
            requestAnimationFrame(step);
          });
        }""",
        [distance, duration_ms],
    )
    return duration_ms / 1000.0


def record_scene(page, scene, pace_config, snapshot_capture=None) -> float:
    """Drive one scene of the recording. When ``snapshot_capture`` is a dict,
    ``page.inner_text("body")`` after networkidle + initial hold is recorded
    under the scene's ``key``, so a sibling QA pass can assert what was
    visible at that moment without OCR'ing the rendered MP4 later.
    """
    url = scene["url"]
    title = scene.get("title", "(scene)")
    print(f"  → {title}: {url}")
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(int(pace_config["initial_hold"] * 1000))

    if snapshot_capture is not None:
        key = scene.get("snapshot_key") or scene.get("title") or url
        try:
            snapshot_capture[key] = page.inner_text("body")
        except Exception as e:  # noqa: BLE001
            snapshot_capture[key] = f"<<snapshot failed: {e}>>"

    hold_override = scene.get("video_hold_seconds")
    if hold_override is not None:
        page.wait_for_timeout(int(float(hold_override) * 1000))
        return pace_config["initial_hold"] + float(hold_override)

    scroll_time = smooth_scroll(page, pace_config)
    page.wait_for_timeout(int(pace_config["final_hold"] * 1000))
    total = pace_config["initial_hold"] + scroll_time + pace_config["final_hold"]

    if total < pace_config["min_hold"]:
        extra = pace_config["min_hold"] - total
        page.wait_for_timeout(int(extra * 1000))
        total = pace_config["min_hold"]
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="walkthrough run JSON")
    ap.add_argument("--spec", required=True, help="walkthrough YAML spec")
    ap.add_argument("--output", required=True, help="output mp4 path")
    ap.add_argument("--cookies", help="optional cookies JSON exported by `browse cookies`")
    ap.add_argument(
        "--storage-state",
        help=(
            "alternative to --cookies: a Playwright storage_state JSON. Used when "
            "the gstack `browse cookies` export isn't available or isn't sticking "
            "across browser contexts. Mutually exclusive with --cookies; if both "
            "are provided, --storage-state wins."
        ),
    )
    ap.add_argument(
        "--snapshot-manifest",
        help=(
            "if set, write `page.inner_text(body)` snapshots taken at each scene "
            "boundary to this JSON path. Pair with verify_video.py to assert each "
            "scene captured what it was supposed to before encoding."
        ),
    )
    args = ap.parse_args()

    ffmpeg = check_ffmpeg()
    run = json.loads(Path(args.input).read_text())
    spec = yaml.safe_load(Path(args.spec).read_text())

    pace_name = spec.get("video_pace", "fast")
    pace_config = PACING.get(pace_name)
    if pace_config is None:
        sys.exit(f"ERROR: video_pace must be one of {list(PACING)} (got: {pace_name!r})")

    viewport_w = int(spec.get("video_viewport_width", 1280))
    viewport_h = int(spec.get("video_viewport_height", 720))

    inject_cursor = bool(spec.get("inject_cursor", False))
    cursor_script: str | None = None
    if inject_cursor:
        if CURSOR_OVERLAY_JS.exists():
            cursor_script = CURSOR_OVERLAY_JS.read_text()
        else:
            print(
                f"  ! inject_cursor: true but {CURSOR_OVERLAY_JS} not found — skipping",
                file=sys.stderr,
            )

    # Pull scene metadata from run JSON; per-scene overrides from spec.scenes
    # (by index — scene_index is 1-based in the run JSON).
    spec_scenes = spec.get("scenes") or []
    scenes = []
    for slide in run.get("slides", []):
        if slide.get("type") != "scene" or not slide.get("url"):
            continue
        idx = slide.get("scene_index", len(scenes) + 1)
        override = None
        spec_key = None
        if 1 <= idx <= len(spec_scenes):
            override = spec_scenes[idx - 1].get("video_hold_seconds")
            spec_key = spec_scenes[idx - 1].get("snapshot_key")
        scenes.append({
            "url": slide["url"],
            "title": slide.get("title", ""),
            "video_hold_seconds": override,
            # Stable key for the snapshot manifest. Prefer an explicit spec
            # field; fall back to scene title (which the matching QA spec
            # can target).
            "snapshot_key": spec_key or slide.get("title", f"scene_{idx}"),
        })

    if not scenes:
        sys.exit("ERROR: no scenes with URLs in run data")

    print(f"Recording {len(scenes)} scenes at pace={pace_name} ({viewport_w}x{viewport_h})")

    with tempfile.TemporaryDirectory(prefix="walkthrough-video-") as td:
        video_dir = Path(td)
        total_seconds = 0.0
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": viewport_w, "height": viewport_h},
                record_video_dir=str(video_dir),
                record_video_size={"width": viewport_w, "height": viewport_h},
            )

            if args.storage_state:
                # Re-create the context with storage_state (Playwright requires
                # this at context-construction time, not via a separate call).
                context.close()
                context = browser.new_context(
                    viewport={"width": viewport_w, "height": viewport_h},
                    record_video_dir=str(video_dir),
                    record_video_size={"width": viewport_w, "height": viewport_h},
                    storage_state=args.storage_state,
                )
            elif args.cookies:
                cookies = json.loads(Path(args.cookies).read_text())
                if cookies:
                    context.add_cookies(cookies)

            if cursor_script:
                context.add_init_script(cursor_script)

            page = context.new_page()

            # If no cookies given and spec has URL-based auth, replay it.
            # Auth nav is NOT held — the recording starts capturing the moment
            # the context opens, but the first scene will mask any auth-page
            # flicker by overwriting it within a second.
            if not args.cookies:
                auth = spec.get("auth") or {}
                if auth.get("type") == "url" and auth.get("url"):
                    base = spec["base_url"].rstrip("/")
                    try:
                        page.goto(base + auth["url"], wait_until="networkidle", timeout=30000)
                    except Exception as e:
                        print(f"  ! auth nav warning: {e}", file=sys.stderr)

            snapshot_capture: dict | None = (
                {} if args.snapshot_manifest else None
            )
            for s in scenes:
                total_seconds += record_scene(page, s, pace_config, snapshot_capture)
                # Write the manifest incrementally so a mid-recording crash
                # still leaves us with verifiable partial data.
                if snapshot_capture is not None and args.snapshot_manifest:
                    Path(args.snapshot_manifest).write_text(
                        json.dumps(snapshot_capture, indent=2)
                    )

            context.close()  # flush video
            browser.close()

        webms = list(video_dir.glob("*.webm"))
        if not webms:
            sys.exit("ERROR: no video file produced by Playwright")
        webm_path = webms[0]

        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"Converting {webm_path.name} → {out_path.name}")
        result = subprocess.run(
            [
                ffmpeg, "-y", "-i", str(webm_path),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-preset", "fast", "-crf", "23",
                str(out_path),
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            sys.exit(f"ERROR: ffmpeg failed (exit {result.returncode}):\n{result.stderr[-2000:]}")

        size_mb = out_path.stat().st_size / (1024 * 1024)
        print(f"✓ {out_path} ({size_mb:.1f} MB, ~{total_seconds:.0f}s of footage)")


if __name__ == "__main__":
    main()
