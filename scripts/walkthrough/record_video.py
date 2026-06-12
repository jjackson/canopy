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
        [--cookies /tmp/walkthrough-cookies.json | --storage-state /tmp/state.json] \\
        [--input /tmp/walkthrough-run-data.json] \\
        [--scene 2,4 | --scene 2-4 | --scene name-match] \\
        [--skip-same-url] \\
        [--report run-report.json] \\
        [--snapshots screenshots/walkthroughs/<name>/] \\
        [--snapshot-empty-scenes] \\
        [--skip-setup]

``--spec`` is the source of truth for scenes. ``--input`` is accepted for
backward compatibility: a walkthrough-run-data.json from canopy:walkthrough
narrows the spec's scenes to the ones that were actually captured (so a
``--scene 3`` partial run records exactly that scene). When ``--input`` is
absent the full spec is recorded.

Specs with a ``setup:`` block (the data-setup contract) get their synthetic
generator command run BEFORE recording — honoring ``rerun: per_render | once``
— and the ``${var}`` placeholders in scene URLs / action targets resolved from
the command's outputs JSON. ``--skip-setup`` skips the command (but still
loads the outputs) for fast re-renders when the data is known-fresh; demos
that mutate state during recording must not use it.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
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

# Placeholder substitution is shared with scripts/ddd/spec_qa.py (single source
# of truth for what `${var}` means) — it lives at the repo root, so put that on
# the path too for by-path invocations (`python3 record_video.py`).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from scripts.narrative.substitution import (  # noqa: E402
    UnresolvedPlaceholderError,
    scenes_placeholders,
    substitute_scenes,
)


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


# --------------------------------------------------------------------------- #
# data setup (spec.setup — the synthetic generator contract)


class SetupError(RuntimeError):
    """The spec's setup command failed (nonzero exit, timeout, bad outputs).

    Raised by :func:`run_setup` so unit tests can assert on it; ``main``
    converts it to a loud ``sys.exit``. A failed setup means the world is NOT
    in a recordable state — rendering anyway films the wrong UI.
    """


def resolve_setup_cwd(spec_path: Path) -> Path:
    """The directory ``setup.command`` runs in.

    The git toplevel containing the spec file (``git rev-parse
    --show-toplevel`` from the spec's directory), falling back to the spec's
    own directory when it isn't in a git repo. Setup commands are written
    repo-root-relative — matching how humans run them — regardless of where
    the recorder itself is invoked from.
    """
    spec_dir = spec_path.resolve().parent
    try:
        result = subprocess.run(
            ["git", "-C", str(spec_dir), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        pass
    return spec_dir


def load_setup_outputs(outputs_path: Path) -> dict:
    """Parse the setup command's outputs JSON into a substitution map.

    The contract is a flat JSON object with string/number values — the
    variables the synthetic generator minted (run IDs, entity IDs, dates).
    Anything else (a list, nested objects, a non-object top level) is a
    :class:`SetupError`: the generator and the spec have drifted, and a vague
    KeyError twelve scenes later would hide that.
    """
    if not outputs_path.exists():
        raise SetupError(
            f"setup outputs file not found: {outputs_path} — the setup command "
            "declared `outputs:` but did not write it (or wrote it elsewhere)."
        )
    try:
        data = json.loads(outputs_path.read_text())
    except json.JSONDecodeError as e:
        raise SetupError(f"setup outputs file is not valid JSON: {outputs_path} ({e})")
    if not isinstance(data, dict):
        raise SetupError(
            f"setup outputs must be a flat JSON object, got {type(data).__name__}: {outputs_path}"
        )
    for key, value in data.items():
        if not isinstance(value, (str, int, float)) or isinstance(value, bool):
            raise SetupError(
                f"setup outputs values must be strings or numbers — "
                f"key '{key}' is {type(value).__name__}: {outputs_path}"
            )
    return data


def run_setup(setup: dict, spec_path: Path, *, skip_setup: bool = False) -> dict:
    """Execute the spec's ``setup`` block and return its provenance record.

    Honors the ``rerun`` semantics: ``per_render`` (default) runs the command
    on every invocation; ``once`` skips it when the outputs file already
    exists. ``skip_setup`` (the ``--skip-setup`` escape hatch) skips the
    command unconditionally but still loads the outputs file — for fast
    re-renders when the operator KNOWS the data is fresh. State-mutating demos
    must not use it: their recording changes the world, so every render needs
    a reseed.

    Output streams to the recorder's log (inherited stdout/stderr — the
    generator's own progress lines show up live). Nonzero exit or timeout
    raises :class:`SetupError`; ``main`` aborts loudly before any browser
    opens.

    Returns the provenance dict that rides on the RunReport and (with
    ``--snapshots``) lands in ``setup-vars.json``: the command, cwd, rerun
    mode, whether/why it was skipped, exit code, duration, and the resolved
    variables. The data a film was made on is part of the run's evidence
    chain.
    """
    command = setup.get("command") or ""
    if not command.strip():
        raise SetupError("spec.setup.command is empty — declare the synthetic generator command")
    rerun = setup.get("rerun", "per_render")
    if rerun not in ("per_render", "once"):
        raise SetupError(f"spec.setup.rerun must be per_render | once (got: {rerun!r})")
    timeout_seconds = int(setup.get("timeout_seconds", 1200))

    cwd = resolve_setup_cwd(spec_path)
    outputs_rel = setup.get("outputs")
    outputs_path = (cwd / outputs_rel) if outputs_rel else None

    provenance: dict = {
        "command": command,
        "cwd": str(cwd),
        "rerun": rerun,
        "outputs": outputs_rel,
        "skipped": False,
        "skip_reason": None,
        "exit_code": None,
        "duration_seconds": None,
        "variables": {},
    }

    skip_reason: str | None = None
    if skip_setup:
        skip_reason = "--skip-setup"
    elif rerun == "once" and outputs_path is not None and outputs_path.exists():
        skip_reason = f"rerun=once and outputs file exists ({outputs_path})"

    if skip_reason:
        provenance["skipped"] = True
        provenance["skip_reason"] = skip_reason
        print(f"Setup: skipped ({skip_reason})")
    else:
        print(f"Setup: running synthetic generator (cwd={cwd}, timeout={timeout_seconds}s)")
        print(f"  $ {command}")
        started = time.monotonic()
        try:
            # No capture: the generator's output streams straight into the
            # recorder's log so a hung seed is visible, not silent.
            result = subprocess.run(
                command, shell=True, cwd=str(cwd), timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - started
            raise SetupError(
                f"setup command timed out after {timeout_seconds}s "
                f"({duration:.0f}s elapsed): {command}"
            )
        duration = time.monotonic() - started
        provenance["exit_code"] = result.returncode
        provenance["duration_seconds"] = round(duration, 2)
        if result.returncode != 0:
            raise SetupError(
                f"setup command failed (exit {result.returncode} after {duration:.0f}s): {command}\n"
                "The world is not in a recordable state — refusing to render."
            )
        print(f"Setup: done in {duration:.1f}s (exit 0)")

    if outputs_path is not None:
        provenance["variables"] = load_setup_outputs(outputs_path)
    return provenance


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

        # Drop a redundant leading ``goto`` action when its target matches
        # ``scene.url`` (after _absolutize) — the orchestrator already
        # navigates to ``scene.url`` at the top of ``run_scene``, so leaving
        # the goto in causes a visible page reload 1-2s into every scene.
        # This was the load-bearing bug behind ~2.5s of scene-start dead-air
        # on every recording.
        #
        # Conservative: only drop the FIRST action, only when it's a goto,
        # only when its absolutized target equals the resolved scene.url.
        # An intentional reload-then-elsewhere pattern (url: /x then
        # goto /y) is preserved — the leading goto's target won't match.
        if url and actions:
            first = actions[0]
            if (first.get("kind") or "") == "goto":
                first_target = _absolutize(first.get("target") or first.get("value") or "")
                if first_target and first_target == url:
                    actions = actions[1:]
                    print(
                        f"  · scene {i}: dropping redundant first goto "
                        f"(target matches scene.url) — use scene.url instead"
                    )

        scenes.append({
            "url": url,  # may be None → orchestrator stays on previous URL
            "title": s.get("title", f"Scene {i}"),
            "video_hold_seconds": s.get("video_hold_seconds"),
            "actions": actions,
            # Optional per-scene viewport override (Scene.viewport in the
            # Pydantic schema). Recorder.run_scene resizes BEFORE the goto if
            # present, restores the spec-level size after the scene's
            # final_hold_ms. None → no override → spec-level viewport.
            "viewport": s.get("viewport"),
            # Per-scene capture mode. ``full_page: false`` → viewport snapshot, for
            # pages that are a tall table + a map/chart (the plan-review page), so the
            # map is the hero instead of a sliver atop a 16,000px strip. Omit (default
            # full-page) for normal pages. Stripping this here was the bug that made
            # map+table scenes capture as unreadable strips.
            "full_page": s.get("full_page"),
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
        "--storage-state",
        help=(
            "alternative to --cookies: a Playwright storage_state JSON (path). "
            "Use when the `browse cookies` export isn't available or isn't "
            "sticking across contexts — storage_state is applied at context "
            "creation, so it also carries localStorage/origins, not just cookies. "
            "Mutually exclusive with --cookies; if both are given, --storage-state wins."
        ),
    )
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
    ap.add_argument(
        "--skip-setup",
        action="store_true",
        help=(
            "skip running spec.setup.command (the synthetic generator) and "
            "just load its outputs file for ${var} substitution. Escape hatch "
            "for fast re-renders when the operator KNOWS the data is fresh. "
            "Demos that MUTATE state during recording must NOT use this — "
            "their scenes change the world, so every render needs a reseed."
        ),
    )
    ap.add_argument(
        "--ddd-orchestrated",
        action="store_true",
        help=(
            "Set by /canopy:ddd-run when it drives the render as part of a DDD "
            "run. Suppresses the hand-drive guard below. Do NOT pass this by "
            "hand — it exists so the orchestrator is the only quiet way to "
            "render into a DDD run dir."
        ),
    )
    ap.add_argument(
        "--force-hand-render",
        action="store_true",
        help=(
            "Override the DDD hand-drive guard and render into a run dir anyway "
            "(e.g. one-off debugging). Prefer /canopy:ddd-run — hand-rendering "
            "does NOT persist the dual-judge verdict to run_state.yaml."
        ),
    )
    args = ap.parse_args()

    # ---- Guardrail: don't hand-drive a DDD run's render ----------------------
    # Calling this recorder directly (instead of going through /canopy:ddd-run)
    # is the #1 way DDD runs end up broken: the dual-judge verdict is never
    # assembled into run_state.yaml, the run can't be resumed cleanly, and
    # ddd-upload has no converged verdict to publish (you get loose /w/ clips,
    # not a navigable /ddd/<slug>/<run_id> package). If the output is landing
    # inside a `.canopy/ddd/runs/<run_id>/` directory, the caller MUST be the
    # orchestrator (--ddd-orchestrated) or explicitly override (--force-hand-render).
    _out_paths = " ".join(
        str(p) for p in (args.snapshots, args.output, args.report) if p
    )
    if ".canopy/ddd/runs/" in _out_paths and not (
        args.ddd_orchestrated or args.force_hand_render
    ):
        sys.exit(
            "\n"
            "════════════════════════════════════════════════════════════════════\n"
            "  ⛔  Refusing to hand-render into a DDD run directory.\n"
            "\n"
            "      This output path lives under .canopy/ddd/runs/. Rendering it\n"
            "      directly bypasses /canopy:ddd-run, so the dual-judge verdict is\n"
            "      NEVER written to run_state.yaml — the run looks stale/done, can't\n"
            "      be resumed cleanly, and ddd-upload publishes loose /w/ clips\n"
            "      instead of a /ddd/<slug>/<run_id> package.\n"
            "\n"
            "      ➜  Run  /canopy:ddd-run <run_id>  instead. It renders AND judges\n"
            "         AND persists run_state in one step, so a later /canopy:ddd\n"
            "         --resume <run_id> just works.\n"
            "\n"
            "      (Standalone /canopy:walkthrough renders OUTSIDE a run dir and is\n"
            "       unaffected. For a deliberate one-off, pass --force-hand-render.)\n"
            "════════════════════════════════════════════════════════════════════\n"
        )

    ffmpeg = check_ffmpeg()
    spec = yaml.safe_load(Path(args.spec).read_text())
    run_data: dict | None = None
    if args.input:
        run_data = json.loads(Path(args.input).read_text())

    # ---- Data setup (spec.setup — the synthetic generator contract) -----------
    # Runs BEFORE any browser/context/page exists: a failed seed must abort the
    # render, and the minted IDs must be substituted into scenes before the
    # first navigation. Never mutates the spec file on disk.
    setup = spec.get("setup") or None
    placeholders = scenes_placeholders(spec.get("scenes") or [])
    setup_provenance: dict | None = None
    if setup:
        try:
            setup_provenance = run_setup(setup, Path(args.spec), skip_setup=args.skip_setup)
        except SetupError as e:
            sys.exit(f"ERROR: {e}")
    elif placeholders:
        # ${...} with no setup block is misconfiguration — there is nothing
        # that could ever resolve these, so filming would navigate to a
        # literal "/runs/${run_id}/" URL.
        sys.exit(
            "ERROR: spec uses ${...} placeholders but declares no `setup:` block: "
            f"{', '.join(sorted(placeholders))}. Declare setup.command + setup.outputs "
            "(the synthetic generator that mints these variables), or remove the placeholders."
        )
    if placeholders or setup_provenance:
        variables = (setup_provenance or {}).get("variables", {})
        try:
            spec["scenes"] = substitute_scenes(spec.get("scenes") or [], variables)
        except UnresolvedPlaceholderError as e:
            sys.exit(f"ERROR: {e}")
        if placeholders:
            print(f"Setup: resolved ${{...}} variables: {', '.join(sorted(placeholders))}")

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
            context_kwargs = dict(
                viewport={"width": viewport_w, "height": viewport_h},
                record_video_dir=str(video_dir),
                record_video_size={"width": viewport_w, "height": viewport_h},
            )
            # storage_state must be supplied at context construction (Playwright
            # can't load it onto an existing context). It seeds the auth before
            # any page opens, so the first scene navigation is already logged in.
            if args.storage_state:
                context_kwargs["storage_state"] = args.storage_state
            context = browser.new_context(**context_kwargs)
            # Synthetic cursor + click ripple (headless Chromium draws no OS
            # cursor). add_init_script runs at document-create on every nav, so
            # the cursor survives the per-scene page changes.
            context.add_init_script(CURSOR_OVERLAY_JS)
            # Auto-accept window.confirm/alert dialogs (e.g. destructive
            # "regenerate?" prompts) so a scripted click doesn't hang the render.
            context.on("dialog", lambda d: d.accept())

            if args.cookies and not args.storage_state:
                cookies = json.loads(Path(args.cookies).read_text())
                if cookies:
                    context.add_cookies(cookies)

            page = context.new_page()
            # Playwright's video capture starts when the page opens — this is
            # second zero of the recording timeline. Captured here (NOT at
            # Recorder.run) so any pre-scene auth navigation below counts
            # toward scene 1's start offset, keeping per-scene timestamps
            # aligned with the produced mp4.
            recording_started = time.monotonic()

            # URL-based auth (e.g. /auth/e2e-login?token=...) for specs that
            # use a magic-link login instead of cookie import. Skipped when
            # --storage-state already seeded the session.
            if not args.cookies and not args.storage_state:
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
                # Per-scene viewport overrides (Scene.viewport) are restored
                # back to this size after each overridden scene's final hold.
                default_viewport={"width": viewport_w, "height": viewport_h},
            )
            recorder.recording_epoch = recording_started
            # Provenance: the data this film is made on is part of the run's
            # evidence chain — the resolved vars + setup command + exit code +
            # duration ride on the RunReport, and land in the snapshots dir.
            recorder.report.setup = setup_provenance
            if args.snapshots and setup_provenance is not None:
                snap_dir = Path(args.snapshots)
                snap_dir.mkdir(parents=True, exist_ok=True)
                (snap_dir / "setup-vars.json").write_text(
                    json.dumps(setup_provenance, indent=2)
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
