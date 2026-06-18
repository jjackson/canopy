#!/usr/bin/env python3
"""Render a connect-videos spec to MP4 locally, on bare metal.

This is canopy's home for the general Remotion video engine's local
renderer. It stages a self-contained ``spec.yaml`` + master clip into the
engine's ``programs/<slug>/runs/<run>/`` tree and runs the host npm render
chain (Node / Chromium / esbuild on the host arch — fast, 1-3 min).

It is the **local-spec** path only — no Drive, no Django container. The
caller (e.g. canopy's DDD ``connect-ddd-walkthrough`` emitter) has already
produced a ``spec.yaml`` and a master clip::

    python render_locally.py --local-spec /path/to/spec.yaml \
        --master /path/to/walkthrough.mp4            # --draft preview
    python render_locally.py --local-spec spec.yaml --master clip.mp4 --final

The slug + run come from the spec (``slug:`` / ``--run``); the master is
copied to the path the spec's ``manifest.master: file:…`` ref names.

The engine project rendered into defaults to this script's own directory
(the canopy ``video-engine``); override with ``--engine-root`` /
``$CONNECT_VIDEOS_ROOT`` to render against a different install.

The server-side / Drive-publish path (the Django ``apps.videos.service``
chain) lives in ace-web, not here — canopy owns only the general,
container-free local render.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# The engine lives in this script's own directory (canopy video-engine).
ENGINE_DIR = Path(__file__).resolve().parent


def engine_root() -> Path:
    """The engine project to render into.

    Defaults to this script's own directory (the canopy video-engine).
    ``$CONNECT_VIDEOS_ROOT`` overrides it so a caller can target a
    different install. (Env var name kept for back-compat with ace-web's
    renderer and existing skills.)
    """
    env = os.environ.get("CONNECT_VIDEOS_ROOT")
    return Path(env).expanduser().resolve() if env else ENGINE_DIR


def load_dotenv_into_env(extra: Path | None = None) -> None:
    """Merge a `.env` into os.environ so the npm render inherits secrets.

    The renderer's per-beat voiceover (ElevenLabs) reads
    ``ELEVENLABS_API_KEY`` from process env. We look in, in order:
    an explicit ``--env-file``, ``./.env`` (cwd), and the engine dir's
    ``.env``. Existing env values always win. Keys with embedded newlines
    are skipped (they'd break naive line parsing).
    """
    candidates = [p for p in (extra, Path.cwd() / ".env", ENGINE_DIR / ".env") if p]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key and key not in os.environ:
                os.environ[key] = value


def host_npm(cv: Path, slug: str, run_id: str, *, draft: bool = True,
             captions: bool = False) -> None:
    """Run the npm render on the host (bare-metal). Stdout streams through.

    ``hydrate`` (Drive asset pull) and the clip-explorer build are omitted:
    a local spec's assets are already local files. ``captions`` defaults
    OFF for connect-ddd-walkthrough renders (the dashboard self-labels and
    the VO narrates); opt in per render.
    """
    render = ["npm", "run", "render", "--", f"--program={slug}", f"--run={run_id}"]
    if draft:
        render.append("--draft")
    if not captions:
        render.append("--no-captions")
    print(f"\n==> {' '.join(render)}")
    subprocess.run(render, cwd=cv, check=True)


def _load_spec(spec_path: Path) -> dict:
    """Parse a program spec. Prefers PyYAML; falls back to a regex reader
    for the two fields we need (top-level ``slug`` + ``manifest.master``)
    so the script runs under a bare stdlib interpreter."""
    text = spec_path.read_text()
    try:
        import yaml  # type: ignore

        doc = yaml.safe_load(text)
        if isinstance(doc, dict):
            return doc
    except Exception:
        pass
    slug_m = re.search(r"^slug:\s*[\"']?([A-Za-z0-9._-]+)", text, re.M)
    master_m = re.search(r"^\s*master:\s*[\"']?(\S+?)[\"']?\s*$", text, re.M)
    return {
        "slug": slug_m.group(1) if slug_m else None,
        "manifest": {"master": master_m.group(1) if master_m else None},
    }


def _copy_into_place(src: Path, dest: Path) -> None:
    """Copy src → dest, no-op when they're already the same file."""
    if dest.exists() and src.resolve() == dest.resolve():
        return
    shutil.copyfile(src, dest)


def stage_local_spec(cv: Path, spec_path: Path, run_id: str, master_path: Path | None) -> str:
    """Stage a local spec + master clip into the engine (no Drive).

    Writes ``programs/<slug>/runs/<run>/spec.yaml`` and copies the master
    clip to the path the spec's ``manifest.master: file:…`` ref names.
    Returns the resolved slug.
    """
    doc = _load_spec(spec_path)
    slug = doc.get("slug")
    if not slug:
        raise SystemExit(f"Could not read `slug` from {spec_path}")

    dest_spec = cv / "programs" / slug / "runs" / run_id / "spec.yaml"
    dest_spec.parent.mkdir(parents=True, exist_ok=True)
    _copy_into_place(spec_path, dest_spec)
    print(f"==> staged spec → {dest_spec}")

    if master_path:
        master_ref = (doc.get("manifest") or {}).get("master") or ""
        if not master_ref.startswith("file:"):
            raise SystemExit(
                f"--master given but spec manifest.master is not a file: ref ({master_ref!r}).\n"
                "Local-spec mode copies the master to the file: path the spec names; "
                "emit the spec with a file: master ref (the DDD emitter does this)."
            )
        # A file: master ref is public-relative (ProgramBody wraps clip.asset
        # in staticFile(), which serves from <engine>/public/). resolveAssetRefs
        # only symlinks *cache* refs into public/ — a file: ref must already
        # live there — so stage the master under public/, not the engine root.
        rel = master_ref[len("file:"):]
        dest_master = cv / "public" / rel
        dest_master.parent.mkdir(parents=True, exist_ok=True)
        _copy_into_place(master_path, dest_master)
        print(f"==> staged master → {dest_master}")

    return slug


def timing_report(cv: Path, slug: str, run_id: str) -> None:
    """Print clip-footage vs actual-duration (the held-frame VO overrun).

    Expected = sum of every beat's ``seconds`` in the spec. Actual = the
    rendered mp4's real duration. A large positive delta means the
    narration outran the footage and the renderer froze the last frame —
    trim narration (~2.2 words/sec for eleven_turbo_v2). Best-effort.
    """
    try:
        import json

        run_dir = cv / "programs" / slug / "runs" / run_id
        spec_text = (run_dir / "spec.yaml").read_text()
        beat_secs = [float(s) for s in re.findall(r"^\s*seconds:\s*([0-9.]+)\s*$", spec_text, re.M)]
        expected = sum(beat_secs)
        out = run_dir / "output.mp4"
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", str(out)],
            capture_output=True, text=True, check=True,
        )
        actual = float(json.loads(probe.stdout)["format"]["duration"])
        overrun = actual - expected
        print("\n==> Timing report")
        print(f"    clip footage (spec beats): {expected:6.1f}s")
        print(f"    rendered duration:         {actual:6.1f}s")
        flag = "  ⚠ VO overruns clips — trim narration to play continuously" if overrun > 3 else ""
        print(f"    held-frame overrun:        {overrun:+6.1f}s{flag}")
    except Exception as e:  # noqa: BLE001 — report is advisory
        print(f"\n==> Timing report skipped ({e})")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--local-spec", required=True,
                   help="Path to a connect-videos spec.yaml to render. "
                        "Slug + run come from the spec.")
    p.add_argument("--master", default=None,
                   help="Master clip copied to the spec's manifest.master file: path.")
    p.add_argument("--run", default=None, help="Run id (default run-001).")
    p.add_argument("--final", action="store_true",
                   help="Render at final quality (skip the default --draft preview).")
    p.add_argument("--captions", action="store_true",
                   help="Burn captions in (default OFF for connect-ddd-walkthrough — "
                        "the dashboard self-labels + the VO narrates).")
    p.add_argument("--engine-root", default=None,
                   help="Override the engine project to render into "
                        "(also honored via $CONNECT_VIDEOS_ROOT).")
    p.add_argument("--env-file", default=None,
                   help="Extra .env to load ELEVENLABS_API_KEY etc. from "
                        "(also checks ./.env and the engine dir's .env).")
    args = p.parse_args()

    if args.engine_root:
        os.environ["CONNECT_VIDEOS_ROOT"] = args.engine_root
    cv = engine_root()
    if not (cv / "package.json").is_file():
        print(f"ERROR: no video engine at {cv}.\n"
              "       Point at an install via --engine-root / $CONNECT_VIDEOS_ROOT.",
              file=sys.stderr)
        return 2

    load_dotenv_into_env(Path(args.env_file) if args.env_file else None)
    if not os.environ.get("ELEVENLABS_API_KEY"):
        print(
            "\nERROR: ELEVENLABS_API_KEY not found in env, --env-file, ./.env, "
            "or the engine dir's .env.\n"
            "       The renderer refuses to render a silent video by default.\n"
            "       Export the key (e.g. from 1Password) and re-run.",
            file=sys.stderr,
        )
        return 2

    run_id = args.run or "run-001"
    print(f"==> local-spec render: spec={args.local_spec} run={run_id} "
          f"quality={'final' if args.final else 'draft'} root={cv}")
    master = Path(args.master) if args.master else None
    slug = stage_local_spec(cv, Path(args.local_spec), run_id, master)

    print("\n==> Run npm render on host (bare-metal)")
    host_npm(cv, slug, run_id, draft=not args.final, captions=args.captions)

    timing_report(cv, slug, run_id)

    out = cv / "programs" / slug / "runs" / run_id / "output.mp4"
    print(f"\n==> Done. Output: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
