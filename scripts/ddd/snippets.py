"""Emit first-class *narrative snippets* from a converged DDD run.

A DDD narrative already carries, per scene/beat, the two things a video snippet
fundamentally needs:

  * **exact in/out timestamps** — from the recorder's per-scene timing
    (``run-report-iter<N>.json`` → ``scenes[].start_seconds`` / ``duration_seconds``);
  * **one clean sentence** — the scene's ``concept_claim`` (a single falsifiable
    beat), which doubles as the caption / lower-third text AND the voiceover script.

So a snippet here is a *logical* range into the run's master walkthrough clip plus
its sentence — NOT a physically re-cut file. The same manifest drives two
downstream consumers in ACE: (a) the first-class snippet *library* (each snippet
stored with its in/out + narration, far richer than a whole-clip + slug), and
(b) the semi-gloss *explainer* render (sequence the ranges, each with per-beat
ElevenLabs VO + a lower-third from the sentence).

This is the canopy/source half of the planned canopy↔ACE narrative substrate,
scoped to the snippet/explainer use case: canopy owns the narrative + timing + the
master clip; ACE owns the library, voice synthesis, and render.

CLI::

    # from the canopy repo, with DDD_DIR pointing at the target repo's .canopy/ddd
    DDD_DIR=/path/to/repo/.canopy/ddd \
      uv run python -m scripts.ddd.snippets emit <run_id> [--iteration N] [--out PATH]

Writes ``<run_dir>/snippet_manifest.json`` and prints it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from scripts.ddd.runstate import _resolve_ddd_dir, load

SCHEMA_VERSION = 1


def _run_dir(run_id: str) -> Path:
    return _resolve_ddd_dir() / "runs" / run_id


def _find_report(run_dir: Path, iteration: int) -> Path:
    """The recorder's run report for *iteration* (per-scene timing lives here)."""
    candidates = [
        run_dir / f"run-report-iter{iteration}.json",
        run_dir / "run-report.json",  # un-suffixed (iteration 0 default)
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        f"no run report found for {run_id_hint(run_dir)} iter {iteration}: "
        f"looked for {[str(c) for c in candidates]}"
    )


def run_id_hint(run_dir: Path) -> str:
    return run_dir.name


def _find_spec(run_dir: Path) -> Path:
    """The unified spec staged into the run dir (concept_claim per scene)."""
    spec = run_dir / "unified_spec.yaml"
    if not spec.exists():
        raise FileNotFoundError(
            f"no unified_spec.yaml in {run_dir} — run /canopy:ddd-upload (which stages it) "
            f"or copy docs/walkthroughs/<slug>.yaml there first."
        )
    return spec


def _slugify(text: str) -> str:
    out = "".join(c.lower() if c.isalnum() else "-" for c in (text or ""))
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:60] or "beat"


def build_snippets(
    *,
    narrative_slug: str,
    spec: dict[str, Any],
    report: dict[str, Any],
    source_clip_local: str | None,
    source_clip_hosted: str | None,
) -> list[dict[str, Any]]:
    """Pair each rendered scene (timing) with its spec scene (sentence)."""
    spec_scenes = spec.get("scenes") or []
    report_scenes = report.get("scenes") or []
    snippets: list[dict[str, Any]] = []

    for rs in report_scenes:
        # run-report scene_index is 1-based; spec scenes are 0-based.
        idx = rs.get("scene_index")
        if idx is None:
            continue
        spec_scene = spec_scenes[idx - 1] if 0 < idx <= len(spec_scenes) else {}
        start = float(rs.get("start_seconds") or 0.0)
        dur = float(rs.get("duration_seconds") or 0.0)
        title = spec_scene.get("title") or rs.get("title") or f"Scene {idx}"
        sentence = (spec_scene.get("concept_claim") or "").strip()
        # The per-scene narrative is the spoken line — it's what the author edits
        # in the narrative review (canopy-web round-trips edits into scene.narrative).
        # concept_claim is the falsifiable design claim, used only as a fallback.
        narration = (spec_scene.get("narrative") or sentence).strip()
        features = spec_scene.get("features") or []
        tags = [narrative_slug] + [
            f.get("id") for f in features if isinstance(f, dict) and f.get("id")
        ]

        snippets.append(
            {
                "id": f"{narrative_slug}-scene-{idx}",
                "scene_index": idx,
                "title": title,
                # Logical range into the master clip — NOT a re-cut file.
                "in_seconds": round(start, 3),
                "out_seconds": round(start + dur, 3),
                "duration_seconds": round(dur, 3),
                # `narration` (scene.narrative) IS the spoken line — the narrative
                # the author writes/edits while picturing the demo. `sentence`
                # (concept_claim) is kept as the design claim / caption fallback.
                "narration": narration,
                "sentence": sentence,
                "tags": tags,
                "provenance": spec_scene.get("provenance"),
                "source_clip": source_clip_local,
                "source_clip_url": source_clip_hosted,
            }
        )
    return snippets


def emit_snippet_manifest(run_id: str, iteration: int | None = None) -> dict[str, Any]:
    """Build the snippet manifest for *run_id* and return it (also written to disk)."""
    state = load(run_id)
    it = iteration if iteration is not None else int(state.iteration)
    run_dir = _run_dir(run_id)

    spec = yaml.safe_load(_find_spec(run_dir).read_text()) or {}
    report = json.loads(_find_report(run_dir, it).read_text())

    clip_local = run_dir / f"iter{it}_clip.mp4"
    hosted = (state.iteration_clips or {}).get(it) or (state.iteration_clips or {}).get(
        str(it)
    )

    snippets = build_snippets(
        narrative_slug=state.narrative_slug,
        spec=spec,
        report=report,
        source_clip_local=str(clip_local) if clip_local.exists() else None,
        source_clip_hosted=hosted,
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "narrative_slug": state.narrative_slug,
        "run_id": run_id,
        "iteration": it,
        "name": spec.get("name") or state.narrative_slug,
        "source_clip": str(clip_local) if clip_local.exists() else None,
        "source_clip_url": hosted,
        "snippet_count": len(snippets),
        "snippets": snippets,
    }
    out = run_dir / "snippet_manifest.json"
    out.write_text(json.dumps(manifest, indent=2))
    manifest["_written_to"] = str(out)
    return manifest


# --------------------------------------------------------------------------
# canopy → ACE bridge: snippet manifest → ace-web "connect-walkthrough" spec.yaml
# --------------------------------------------------------------------------
# The ACE walkthrough-explainer template (templates/connect-walkthrough) renders
# ONE master clip narrated section-by-section: a `beats:` list (intro_title →
# body_walkthrough×N → outro_card) drives the arc, each body_walkthrough beat
# plays a RANGE of the master clip (walkthrough.<id>.{start_seconds,
# duration_seconds, lower_third}) with per-beat ElevenLabs VO
# (narration.by_beat.<id>). Our snippets map onto it 1:1 — in/out → the clip
# range, title → lower_third, sentence → VO. See the ace-web template's
# example.spec.yaml for the canonical shape this mirrors.

# ElevenLabs defaults match ace-web's connect-walkthrough example.spec.yaml.
DEFAULT_VOICE_ID = "XB0fDUnXU5powFXDhCwa"
DEFAULT_VOICE_MODEL = "eleven_turbo_v2"


def build_explainer_spec(
    manifest: dict[str, Any],
    *,
    workspace: str,
    master_ref: str,
    base_url: str,
    tagline: str,
    country_focus: str,
    voice_id: str = DEFAULT_VOICE_ID,
    voice_model: str = DEFAULT_VOICE_MODEL,
    generated_at: str = "1970-01-01T00:00:00Z",
    lower_thirds: bool = False,
) -> dict[str, Any]:
    """Map a snippet manifest onto an ace-web connect-walkthrough spec dict."""
    slug = manifest["narrative_slug"]
    name = manifest.get("name") or slug
    snippets = manifest.get("snippets") or []

    beats: list[dict[str, Any]] = [{"id": "title", "kind": "intro_title", "seconds": 4}]
    walkthrough: dict[str, Any] = {}
    by_beat: dict[str, str] = {
        "title": f"{name}: {tagline}".strip().rstrip(":") if tagline else name
    }

    for sn in snippets:
        bid = f"s{sn['scene_index']}"
        beats.append(
            {"id": bid, "kind": "body_walkthrough", "seconds": round(sn["duration_seconds"], 1)}
        )
        walkthrough[bid] = {
            "asset": "@master",
            "start_seconds": sn["in_seconds"],
            "duration_seconds": sn["duration_seconds"],
            # Off by default — the recorded dashboard self-labels and the VO
            # narrates, so a lower-third pill just covers the content. Opt in
            # with --lower-thirds.
            "lower_third": sn["title"] if lower_thirds else "",
        }
        # Spoken line = the scene's narration (what the author edits in review).
        # The renderer holds the section's last frame if narration runs longer
        # than the clip range, so the narrative can be any length without drift.
        by_beat[bid] = sn.get("narration") or sn.get("sentence") or ""
    beats.append({"id": "outro", "kind": "outro_card", "seconds": 5})
    by_beat["outro"] = ""

    return {
        "provenance": {
            "generator": "video-from-walkthrough",
            "template": "connect-walkthrough",
            "generated_from": f"{slug} DDD run {manifest.get('run_id')}",
            "generated_at": generated_at,
        },
        "slug": f"{slug}-explainer",
        "workspace": workspace,
        "name": name,
        "country_focus": country_focus,
        "status": "DDD walkthrough",
        "tagline": tagline,
        "program_url": base_url,
        "manifest": {"master": master_ref},
        "beats": beats,
        "walkthrough": walkthrough,
        "narration": {
            "generator": "manual",
            "prompt_version": "v1",
            "start_seconds": 0,
            "by_beat": by_beat,
            # Full VO blob (required by ProgramSpecSchema) — the per-beat
            # sentences in timeline order, so script and by_beat never drift.
            "script": "\n".join(
                by_beat[b["id"]] for b in beats if by_beat.get(b["id"])
            ),
        },
        "voice": {"provider": "elevenlabs", "voice_id": voice_id, "model": voice_model},
    }


def emit_explainer_spec(
    run_id: str,
    *,
    iteration: int | None = None,
    workspace: str = "dimagi-team",
    master_ref: str | None = None,
    tagline: str = "",
    country_focus: str = "",
    lower_thirds: bool = False,
) -> dict[str, Any]:
    """Build the explainer spec for *run_id* and write explainer_spec.yaml."""
    manifest = emit_snippet_manifest(run_id, iteration=iteration)
    run_dir = _run_dir(run_id)

    # base_url + a tagline default come from the unified spec when present.
    spec = yaml.safe_load(_find_spec(run_dir).read_text()) or {}
    base_url = spec.get("base_url") or "https://labs.connect.dimagi.com/"
    if not tagline:
        tagline = spec.get("tagline") or ""

    # Default the master ref to a library: path (operator uploads the master
    # clip + runs videos_ingest_snippets which links it). Fall back to the
    # hosted clip URL if present, else a file: basename.
    if not master_ref:
        if manifest.get("source_clip_url"):
            master_ref = manifest["source_clip_url"]
        elif manifest.get("source_clip"):
            master_ref = f"library:video/ddd/{Path(manifest['source_clip']).name}"
        else:
            master_ref = f"library:video/ddd/{manifest['narrative_slug']}.mp4"

    explainer = build_explainer_spec(
        manifest,
        workspace=workspace,
        master_ref=master_ref,
        base_url=base_url,
        tagline=tagline,
        country_focus=country_focus,
        lower_thirds=lower_thirds,
    )
    out = run_dir / "explainer_spec.yaml"
    out.write_text(yaml.safe_dump(explainer, sort_keys=False, allow_unicode=True))
    explainer["_written_to"] = str(out)
    return explainer


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="scripts.ddd.snippets")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("emit", help="emit the snippet manifest for a run")
    e.add_argument("run_id")
    e.add_argument("--iteration", type=int, default=None)

    x = sub.add_parser(
        "explainer-spec", help="emit an ace-web connect-walkthrough spec.yaml from a run"
    )
    x.add_argument("run_id")
    x.add_argument("--iteration", type=int, default=None)
    x.add_argument("--workspace", default="dimagi-team")
    x.add_argument("--master-ref", default=None, help="manifest ref for the master clip (library:/file:/gdrive:/url)")
    x.add_argument("--tagline", default="")
    x.add_argument("--country", dest="country_focus", default="")
    x.add_argument("--lower-thirds", dest="lower_thirds", action="store_true",
                   help="overlay a lower-third title pill per section (default off — clean dashboard)")

    args = p.parse_args(argv)

    if args.cmd == "emit":
        manifest = emit_snippet_manifest(args.run_id, iteration=args.iteration)
        print(json.dumps(manifest, indent=2))
    elif args.cmd == "explainer-spec":
        explainer = emit_explainer_spec(
            args.run_id,
            iteration=args.iteration,
            workspace=args.workspace,
            master_ref=args.master_ref,
            tagline=args.tagline,
            country_focus=args.country_focus,
            lower_thirds=args.lower_thirds,
        )
        print(yaml.safe_dump(explainer, sort_keys=False, allow_unicode=True))


if __name__ == "__main__":
    main()
