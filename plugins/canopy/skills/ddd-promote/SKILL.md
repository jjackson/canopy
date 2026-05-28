---
name: ddd-promote
description: |
  Promote a converged DDD run (SP7) to a published documentation page:
  upload the hero video, build a self-contained HTML docs page (hero video +
  capabilities + why + how for a prospective feature user), run the
  external_release review gate, then publish the page to canopy-web.
  Phase transitions from "converged" → "promoted" on publish; no-op on hold.
  Use when asked to "promote this run", "publish the docs page", or "run SP7".
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue — do not block on the upgrade.

# DDD Promote — SP7

Terminal step of the DDD loop: once a run has converged, PROMOTE it to the
published documentation artifact for prospective users of the feature.

## Inputs

- **`run_id`** — an existing converged run identifier.  The run directory must
  already exist at `<ddd_dir>/runs/<run_id>/` and contain:
  - `run_state.yaml` (phase should be `converged`)
  - `unified_spec.yaml`
  - `why_brief.yaml`
- **`video_path`** — local filesystem path to the hero video `.mp4` produced by
  the converged walkthrough render step.

## What the docs page contains

The generated HTML is a **self-contained, no-external-deps documentation page**
aimed at a **prospective user of the feature** — not an internal reviewer, not a
developer.  Sections, in order:

1. **Hero video** at the top: the converged walkthrough recording embedded as a
   `<video>` (direct .mp4 / data URI) or `<iframe>` (canopy-web share page URLs
   containing `/w/`).
2. **What you can do** — one bullet per scene's `concept_claim`.  Capabilities.
3. **Why it works this way** — the `why_brief.problem` context followed by each
   `spine[].claim` + `spine[].rationale`.  Grounded reasoning.
4. **How to use it** — numbered steps from each scene's `show` field, in scene
   order.  Instructional.

All user-supplied text is HTML-escaped (no XSS).

> **Remotion glossy render is explicitly deferred.**  The current docs page is
> plain HTML — no Remotion, no ace-web, no MP4 generation from slides.  That
> upgrade is planned but out of scope for SP7.

## Procedure

### Step 1 — Run the promotion script

```bash
python -m scripts.ddd.promote <run_id> --video <video_path>
```

The script orchestrates all steps internally:

1. Loads `run_state.yaml` + `unified_spec.yaml` + `why_brief.yaml` from the run dir.
2. Uploads the hero video to canopy-web → `video_url`.
3. Builds the docs HTML via `build_docs_page(spec, why_brief, video_url)`.
4. Opens the **external_release** review gate (see below).
5. On `"publish"`: uploads the HTML → `docs_url`, sets `phase = "promoted"`, saves.
6. On `"hold"`: returns without publishing; phase stays unchanged.

### Step 2 — External release gate

The gate presents a `ReviewRequest` with:

```
gate: "external_release"
decisions:
  - id: publish
    prompt: "Publish this docs page for users?"
    options: [publish, hold]
    recommended: publish
    class: external_release
```

The review is posted to canopy-web and the script waits for human resolution.

**Outcomes:**

| Decision | Effect |
|----------|--------|
| `publish` | HTML is uploaded, `phase = "promoted"`, docs URL is returned |
| `hold`    | No HTML upload, phase unchanged, script exits with empty string |

If the human chose `hold`, tell the user:

```
Promotion held — the docs page was not published.
Review the hero video and the docs HTML preview, make any corrections, then
re-run /canopy:ddd-promote when ready.
```

### Step 3 — Report

On successful publish:

```
DDD Promote — <run_id>
══════════════════════════════════════
  Run dir: <run_dir>

  Hero video:    <video_url>
  Docs page:     <docs_url>

  phase → promoted
```

Tell the user: "Feature documentation published. Share `<docs_url>` with
prospective users."

## Output artefacts

| Artefact | Notes |
|----------|-------|
| `run_state.yaml` (phase=promoted) | Written on successful publish only |
| Docs page on canopy-web | Self-contained HTML; link-visible by default |
| Hero video on canopy-web | Uploaded first; URL embedded in the docs page |
