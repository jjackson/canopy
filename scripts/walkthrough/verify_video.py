#!/usr/bin/env python3
"""verify_video.py — QA harness for canopy:walkthrough video recordings.

Two layers of verification, in order of strength:

1. **Inline scene snapshots (preferred)** — when ``record_video.py`` is run
   with ``--snapshot-manifest <path>``, it writes the visible ``page.inner_text``
   captured at each scene boundary. This script reads that manifest and
   asserts every scene contains its required text + lacks forbidden text.
   Catches "stuck on wrong page" / "loading screen left in the recording"
   bugs **before encoding**, so a broken recording never gets shipped.

2. **OCR fallback** — if no inline snapshots are present, sample the final
   MP4 at each scene's midpoint timestamp and OCR via tesseract (when
   available) or fall back to a frame-size heuristic (loading screens
   compress small).

The expected-content spec is per-walkthrough. Either pass ``--spec-file
<expectations.json>`` pointing at a JSON file like::

    {
      "scenes": [
        {
          "key": "grid",
          "name": "Dashboard grid",
          "required_text": ["Total FLWs", "SAM Rate"],
          "forbidden_text": ["Loading"]
        },
        ...
      ]
    }

…or let the script discover a sidecar ``<walkthrough-name>.qa.json`` next
to your spec.

Usage::

    verify_video.py /tmp/walkthrough-scene-snapshots.json --spec-file qa.json
    verify_video.py screenshots/walkthroughs/demo.mp4 --spec-file qa.json
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Scene:
    key: str
    name: str
    required_text: list[str]
    forbidden_text: list[str]


def load_scenes(spec_path: Path) -> list[Scene]:
    raw = json.loads(spec_path.read_text())
    out: list[Scene] = []
    for s in raw.get("scenes", []):
        out.append(
            Scene(
                key=s["key"],
                name=s.get("name", s["key"]),
                required_text=list(s.get("required_text") or []),
                forbidden_text=list(s.get("forbidden_text") or []),
            )
        )
    if not out:
        sys.exit(f"ERROR: no scenes in {spec_path}")
    return out


def check_inline_snapshots(manifest_path: Path, scenes: list[Scene]) -> int:
    raw = json.loads(manifest_path.read_text())
    print(f"Inline snapshots: {manifest_path}  ({len(raw)} scenes captured)\n")
    failures: list[tuple[str, list[str]]] = []
    for scene in scenes:
        captured = raw.get(scene.key)
        if captured is None:
            print(f"✗ {scene.name}")
            print(f"   · scene key {scene.key!r} not in manifest — recorder may have crashed early")
            failures.append((scene.name, ["scene not captured by recorder"]))
            continue
        text = captured.lower()
        errors: list[str] = []
        for need in scene.required_text:
            if need.lower() not in text:
                errors.append(f"missing required text: {need!r}")
        for forbid in scene.forbidden_text:
            if forbid.lower() in text:
                errors.append(f"contains forbidden text: {forbid!r}")
        marker = "✓" if not errors else "✗"
        print(f"{marker} {scene.name}")
        for e in errors:
            print(f"   · {e}")
        if errors:
            failures.append((scene.name, errors))

    print()
    if failures:
        print(f"❌ {len(failures)}/{len(scenes)} scene(s) failed verification")
        return 1
    print(f"✓ All {len(scenes)} scenes verified")
    return 0


def have_tesseract() -> bool:
    return shutil.which("tesseract") is not None


def ocr(png_path: Path) -> str:
    try:
        out = subprocess.run(
            ["tesseract", str(png_path), "-", "--psm", "6"],
            capture_output=True, text=True, timeout=30,
        )
        return out.stdout
    except Exception as e:
        print(f"  ! tesseract failed on {png_path.name}: {e}")
        return ""


def check_mp4_fallback(video_path: Path, scenes: list[Scene]) -> int:
    if not shutil.which("ffmpeg"):
        sys.exit("ERROR: ffmpeg not on PATH — required for MP4 fallback")
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True,
    ).stdout.strip())
    print(f"MP4 fallback verification: {video_path}  ({duration:.1f}s)")
    use_ocr = have_tesseract()
    if not use_ocr:
        print("  ⚠ tesseract not installed — falling back to frame-size heuristic.")
        print("    Install with: brew install tesseract (macOS) / apt-get install tesseract-ocr (Linux)")
    print()

    # Sample at uniform intervals across the video duration.
    failures: list[tuple[str, list[str]]] = []
    frames_dir = video_path.parent / "_qa_frames"
    frames_dir.mkdir(exist_ok=True)
    step = duration / max(1, len(scenes))
    for i, scene in enumerate(scenes):
        t = step * (i + 0.5)
        frame_path = frames_dir / f"qa_{scene.key}_{t:.1f}s.png"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-i", str(video_path), "-ss", f"{t:.2f}",
             "-frames:v", "1", str(frame_path)],
            check=True,
        )
        errors: list[str] = []
        if use_ocr:
            text = ocr(frame_path).lower()
            for need in scene.required_text:
                if need.lower() not in text:
                    errors.append(f"missing required text: {need!r}")
            for forbid in scene.forbidden_text:
                if forbid.lower() in text:
                    errors.append(f"contains forbidden text: {forbid!r}")
        else:
            size = frame_path.stat().st_size
            if size < 180_000:
                errors.append(f"frame is suspiciously small ({size} bytes) — likely a loading screen")
        marker = "✓" if not errors else "✗"
        print(f"{marker} {scene.name} (t={t:.1f}s)")
        for e in errors:
            print(f"   · {e}")
        if errors:
            failures.append((scene.name, errors))

    print()
    if failures:
        print(f"❌ {len(failures)}/{len(scenes)} scene(s) failed verification")
        return 1
    print(f"✓ All {len(scenes)} scenes verified")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    ap.add_argument("target", help="path to scene-snapshots JSON or MP4")
    ap.add_argument("--spec-file", required=True, help="path to QA spec JSON")
    args = ap.parse_args()

    target = Path(args.target)
    spec = Path(args.spec_file)
    if not target.exists():
        print(f"❌ target not found: {target}")
        return 2
    if not spec.exists():
        print(f"❌ spec not found: {spec}")
        return 2
    scenes = load_scenes(spec)
    if target.suffix == ".json":
        return check_inline_snapshots(target, scenes)
    # MP4 fallback
    sidecar = target.parent / f"{target.stem}-scene-snapshots.json"
    if sidecar.exists():
        return check_inline_snapshots(sidecar, scenes)
    return check_mp4_fallback(target, scenes)


if __name__ == "__main__":
    sys.exit(main())
