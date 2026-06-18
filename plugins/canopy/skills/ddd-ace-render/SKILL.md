---
name: ddd-ace-render
description: >
  Use when you want a DDD narrative turned into a narrated
  connect-ddd-walkthrough video on demand — record a fresh master clip,
  emit the explainer spec, and hand off to the local ace renderer. This is
  the standalone "render this narrative as an ace video" command; it is NOT
  part of the automatic DDD loop and does not publish.
---

# DDD → ace render (connect-ddd-walkthrough)

Turn one DDD narrative into a narrated `connect-ddd-walkthrough` MP4. This
command does three things and stops: **record a fresh master clip**, **emit
the explainer spec** (canopy owns this), and **hand the spec + clip to the
local ace renderer** (`/ace:video-render-local`, which wraps ace-web's
`render_locally.py`). The narration is each scene's `scene.narrative`; the
renderer holds a clip's last frame when its VO overruns, so the timing
report at the end tells you whether to trim.

## When to use
- You have a DDD narrative spec (`docs/walkthroughs/<slug>.yaml`) and want the narrated video, now.
- You changed the narration and want to re-render against fresh footage.
- NOT the auto loop (that's `/canopy:ddd-run`), NOT publishing (that's `/canopy:ddd-upload`).

## Prerequisites
- Run from the **project repo** that owns the narrative (e.g. connect-labs) — the spec's `setup:` reseeds there.
- A live browse session authenticated to the target app, for session-auth specs (see `/canopy:walkthrough` setup).
- The **ace side**: an ace-web checkout with connect-videos deps installed + `ELEVENLABS_API_KEY` (the `/ace:video-render-local` skill documents this).
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

**3. Hand off to the local ace renderer.** Invoke the **`/ace:video-render-local`**
skill in Mode A with the emitted spec + the recorded clip:
```
/ace:video-render-local  --local-spec <WORK>/explainer_spec.yaml  --master <WORK>/master.mp4  --final
```
(Concretely that runs `python "${ACE_WEB_ROOT:-$HOME/emdash-projects/ace-web}/scripts/render_locally.py" --local-spec … --master … --final`.) Follow that skill — it resolves the checkout, ensures the ElevenLabs key + connect-videos deps, renders, and prints the output path.

**4. Report** the output MP4 path and the renderer's timing report (clip
footage vs rendered duration vs held-frame overrun). If the overrun is large,
the narration outruns the footage — trim `scene.narrative` (~2.2 words/sec for
the ElevenLabs voice) and re-run.

## Common mistakes
- **Wrong cwd** — run from the project repo that owns `docs/walkthroughs/<slug>.yaml`; the recorder's `setup:` reseeds there. The canopy emit is invoked from the canopy checkout with absolute paths (the snippet above handles the `cd`).
- **Stale narration** — the VO is `scene.narrative` in the live spec; edit it there (or via canopy-web → `narrative pull`) before rendering.
- **Skipping the fresh capture** — this command records new footage on purpose; don't point it at an old clip if the dashboard/data changed.

## Relationship to other commands
- `/canopy:ddd-run` — the auto loop (render + judge); this is the on-demand narrated-video render, separate from it.
- `/ace:video-render-local` — the general local renderer this hands off to.
- `/canopy:ddd-upload` — publishes a converged run; unaffected (keeps using its own hero video).
