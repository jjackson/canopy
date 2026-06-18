---
name: ddd-ace-render
description: >
  Use when you want a DDD narrative turned into a narrated
  connect-ddd-walkthrough video on demand — record a fresh master clip,
  emit the explainer spec, hand off to the local ace renderer, and attach the
  video to the narrative's current version on canopy-web. This is the
  standalone "render this narrative as an ace video" command; it is NOT part
  of the automatic DDD loop. The upload is on by default; pass --no-upload to
  render locally without publishing.
---

# DDD → ace render (connect-ddd-walkthrough)

Turn one DDD narrative into a narrated `connect-ddd-walkthrough` MP4. This
command does three things and stops: **record a fresh master clip**, **emit
the explainer spec**, and **render it with canopy's own video engine**
(`video-engine/render_locally.py` — the general Remotion engine; canopy owns
record → spec → render end-to-end, no ace-web checkout needed). The narration
is each scene's `scene.narrative`; the renderer holds a clip's last frame when
its VO overruns, so the timing report at the end tells you whether to trim.

## When to use
- You have a DDD narrative spec (`docs/walkthroughs/<slug>.yaml`) and want the narrated video, now.
- You changed the narration and want to re-render against fresh footage.
- NOT the auto loop (that's `/canopy:ddd-run`), NOT publishing (that's `/canopy:ddd-upload`).

## Prerequisites
- Run from the **project repo** that owns the narrative (e.g. connect-labs) — the spec's `setup:` reseeds there.
- A live browse session authenticated to the target app, for session-auth specs (see `/canopy:walkthrough` setup).
- The **video engine deps**: `video-engine/node_modules` installed (run `/canopy:setup`, or `cd video-engine && npm ci`) + `ELEVENLABS_API_KEY` in env / `--env-file` / a `.env` (e.g. from 1Password). The renderer refuses to render silent.
- `ffmpeg` + `playwright` (the canopy recorder's deps).

## Procedure

Resolve the spec and the canopy scripts:
```bash
SLUG="<narrative-slug>"                 # e.g. verified-monitoring
SPEC="docs/walkthroughs/$SLUG.yaml"     # in the current project repo
[ -f "$SPEC" ] || { echo "no spec at $SPEC — run from the project repo that owns the narrative"; exit 1; }

# canopy checkout (dev first, then marketplace clone)
for C in ~/emdash-projects/canopy ~/.claude/plugins/marketplaces/canopy; do
  [ -f "$C/scripts/walkthrough/record_video.py" ] && CANOPY="$C" && break
done
WORK="$(mktemp -d)"
```

**1. Record a fresh master clip.** Same recorder `/canopy:walkthrough` uses
(it reseeds via the spec's `setup:` and films one continuous take). Export
live cookies first for session-auth specs:
```bash
$B cookies > "$WORK/cookies.json"          # $B = the browse binary (see /canopy:walkthrough)
python3 "$CANOPY/scripts/walkthrough/record_video.py" \
  --spec "$SPEC" \
  --output   "$WORK/master.mp4" \
  --report   "$WORK/report.json" \
  --manifest "$WORK/manifest.json" \
  --snapshots "$WORK/frames/" \
  --cookies  "$WORK/cookies.json"
```

**2. Emit the connect-ddd-walkthrough spec** from the fresh capture (no
run-state needed — slug comes from the spec's `name`):
```bash
( cd "$CANOPY" && python3 -m scripts.ddd.snippets explainer-from-capture \
    "$(cd "$OLDPWD" && pwd)/$SPEC" "$WORK/report.json" \
    --clip "$WORK/master.mp4" --out "$WORK/explainer_spec.yaml" )
```
This writes `explainer_spec.yaml`: per-beat clip ranges from the report,
`scene.narrative` as the per-beat VO, `manifest.master: file:…`, David voice.

**3. Render with canopy's video engine.** Run canopy's own
`video-engine/render_locally.py` (Mode A — local spec + master, no Drive, no
container) with `ELEVENLABS_API_KEY` in the environment:
```bash
ELEVENLABS_API_KEY="$(…fetch the key…)" \
python3 "$CANOPY/video-engine/render_locally.py" \
  --local-spec "$WORK/explainer_spec.yaml" \
  --master     "$WORK/master.mp4" \
  --final            # omit for a faster --draft preview
```
Output lands at
`video-engine/programs/<slug>/runs/<run>/output.mp4`. The script stages the
spec + master, runs the host npm render (bare-metal — 1-3 min), and prints a
timing report (clip footage vs rendered duration vs held-frame VO overrun).
(`--engine-root` / `$CONNECT_VIDEOS_ROOT` overrides the engine location.)

**4. Report** the output MP4 path and the renderer's timing report (clip
footage vs rendered duration vs held-frame overrun). If the overrun is large,
the narration outruns the footage — trim `scene.narrative` (~2.2 words/sec for
the ElevenLabs voice) and re-run.

**5. Upload to the narrative (default — skip only with `--no-upload`).** Attach
the **rendered** mp4 (the ace renderer's `output.mp4`, not the silent master) to
the narrative's **current version** on canopy-web. This runs by default; pass
`--no-upload` to render locally without publishing:
```bash
( cd "$CANOPY" && python3 -m scripts.ddd.snippets upload-video "$SLUG" "<output.mp4>" )
```
It resolves the current narrative version, uploads the mp4 as a `kind=video`
walkthrough stamped with that version's review id (`narrative_review_id`), and
prints the narrative URL. Pinning to the version means a later narration edit
can't leave a stale video on a newer version. Refuses if canopy-web has no
narrative version for the slug — post the narrative through the narrative-review
gate first.

## Common mistakes
- **Wrong cwd** — run from the project repo that owns `docs/walkthroughs/<slug>.yaml`; the recorder's `setup:` reseeds there. The canopy emit is invoked from the canopy checkout with absolute paths (the snippet above handles the `cd`).
- **Stale narration** — the VO is `scene.narrative` in the live spec; edit it there (or via canopy-web → `narrative pull`) before rendering.
- **Skipping the fresh capture** — this command records new footage on purpose; don't point it at an old clip if the dashboard/data changed.

## Relationship to other commands
- `/canopy:ddd-run` — the auto loop (render + judge); this is the on-demand narrated-video render, separate from it.
- `video-engine/render_locally.py` — canopy's own general Remotion renderer this calls (Mode A: local spec + master).
- `/ace:video-render-local` — ace-web's server/Drive-publish render path (Mode B); use it when publishing to Drive/labs, not for the local DDD render.
- `/canopy:ddd-upload` — publishes a converged run; unaffected (keeps using its own hero video).
