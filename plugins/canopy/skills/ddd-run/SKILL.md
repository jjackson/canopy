---
name: ddd-run
description: |
  Render + dual-verdict run (SP4). Orchestrates the full render-then-judge
  sequence for a DDD run: gates on ddd-spec-qa, invokes canopy:walkthrough to
  render the unified_spec into per-scene screenshots + captured page text, then
  dispatches the concept judge (ddd-concept-eval → verdict-concept.yaml +
  design_findings.json) and user-artifact judge (canopy:visual-judge with
  audience="feature user" → verdict-user.yaml) in parallel. Assembles both
  verdicts into run_state.yaml via run_pipeline.assemble_run_state, reports
  convergence via run_pipeline.compute_convergence, and prints the two
  overall_scores + top findings.
  Use when asked to "run the ddd walkthrough", "render and judge", or "run SP4".
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# DDD Run — Render + Dual-Verdict

Drives the full render-then-judge sequence for a single DDD iteration:
gate → render → judge (concept + user-artifact in parallel) → assemble → report.

## Inputs

- **`run_id`** — an existing run identifier from `scripts.ddd.runstate.new_run`.
  The run directory must already exist at `<ddd_dir>/runs/<run_id>/`.
- **`unified_spec`** — path to `unified_spec.yaml`.  This IS a runnable canopy
  walkthrough spec — the render step drives it directly via `canopy:walkthrough`.
- **`why_brief`** — path to `why_brief.yaml` (needed by the concept judge for
  provenance cross-checks).
- **`--scene <selector>`** *(optional)* — render only a subset of scenes.
  Same selector grammar as `/canopy:walkthrough --scene`. Use when the
  iteration that just landed only touched one scene's feature and a
  full-spec run would mostly re-render unchanged scenes. The full
  dual-judge rubric still applies — only the render step is filtered.
  When set, `run_state.yaml` carries `scenes_run` (the original 1-based
  spec indices actually rendered) and `scene_filter` (the raw selector)
  so convergence reports and upload checks can tell partial runs from
  full ones. **Upload (`/canopy:ddd-upload`) requires a full run** —
  a partial run cannot be uploaded as a feature package.

## Procedure

### Step 1 — Gate: spec QA

Before rendering, verify the spec is structurally sound (the script lives in the
canopy repo):

```bash
# scripts/ddd ships in the canopy repo, not the plugin cache — resolve it:
DDD_REPO="$HOME/emdash-projects/canopy"; [ -d "$DDD_REPO/scripts/ddd" ] || DDD_REPO="$HOME/.claude/plugins/marketplaces/canopy"
if [ ! -d "$DDD_REPO/scripts/ddd" ]; then echo "ERROR: scripts/ddd not found — run /canopy:update to sync the canopy checkout"; exit 1; fi
# pass the file arg as an absolute path (resolved before the cd):
UNIFIED_SPEC_ABS="$(realpath <unified_spec>)"
(cd "$DDD_REPO" && uv run python -m scripts.ddd.spec_qa "$UNIFIED_SPEC_ABS")
```

If the exit code is non-zero (verdict: fail), stop immediately and tell the user:

```
ddd-run: BLOCKED — ddd-spec-qa must pass before rendering.
  blocking_reason: <spec_qa blocking_reason>
  Fix the structural issues, re-run /canopy:ddd-spec-qa, then retry /canopy:ddd-run.
```

Do NOT render a spec that fails the QA gate.

### Step 2 — Render: invoke the canopy walkthrough engine

Invoke `canopy:walkthrough` (or the equivalent Skill tool call) against
`<unified_spec>` to drive the live product and produce:

- `scene_<N>.png` — per-scene screenshot for each scene in the spec.
- `scene_<N>_page_text.json` — captured page text (`$B text` output) per scene.
- The walkthrough JSON sidecar into the run dir.

If invoked with `--scene <selector>`, pass it through verbatim to
`canopy:walkthrough` so only the matching scenes get rendered. The skill
preserves original scene_index in filenames (so `--scene 2` produces
`scene_2.png` and `scene_2_page_text.json`, not `scene_1.png`), keeping
artifact paths stable across partial and full runs.

All output lands in the run directory (`<ddd_dir>/runs/<run_id>/`).

> **Live labs note:** For live Connect Labs features, the render step also
> requires the connect-labs recorder rig, a freshness guard (confirming the
> deployed code is current), and a seeded demo.  Those are wired in the
> rooftop run — not here.  For dry runs and unit tests, the render step is
> exercised separately.

#### Recording CLI flag matrix

The `canopy:walkthrough` skill drives `scripts/walkthrough/record_video.py`
under the hood. Several CLI flags are author-controlled and matter for a DDD
run specifically — the defaults are tuned for one-off `/canopy:walkthrough`
calls, not for the dual-judge pipeline. When invoking the recorder, pass the
flags below.

| Flag | When to pass | Why |
| --- | --- | --- |
| `--cookies <path>` | Always when the spec's `auth: type: session` | Without this the recorder hits the login wall. |
| `--snapshots <dir>` | **Always** for DDD runs | Concept-eval needs per-scene PNG + page_text JSON inputs. The visual-judge can't dual-judge without them. |
| `--snapshot-empty-scenes` | Almost never | Empty scenes (narrative-only back-halves) have no meaningful state to snapshot. |
| `--report <path>` | Always | The accumulator JSON tells you which actions silently failed (and which `must_succeed` ones aborted). |
| `--skip-empty-scenes` | When the spec has narrative-only back-half scenes (no `actions`) | The mp4 doesn't waste `min_hold_ms` on identical static pages. Deck slides still cover them. |
| `--skip-same-url` | When the spec uses continue-scene patterns (scenes that operate on the previous scene's URL) | Avoids re-navs that wipe JS state between scenes. |
| `--input <run.json>` | Only for `--scene` partial runs (when reusing a previous walkthrough's capture set) | Without this, the spec is the only source of truth. |

**DDD orchestrator default flag set** — what `/canopy:ddd-run` should pass to
`record_video.py`:

```bash
python3 "$REC" \
  --input "<run_dir>/walkthrough-run-data.json" \
  --spec "<unified_spec>" \
  --output "<run_dir>/iter${state.iteration}_clip.mp4" \
  --cookies "<session-cookies>" \
  --snapshots "<run_dir>/snapshots/" \
  --report "<run_dir>/run-report.json" \
  --skip-empty-scenes \
  --skip-same-url
```

After the recorder exits, scan `<run_dir>/run-report.json` for non-zero
`failed` counts before letting the judges run. A scene whose
`must_succeed: true` action failed will surface here as an `ok: false`
result with a clear `error_kind` — that's the orchestrator's signal to
either retry the render or treat the scene as blocked, not to grade a
half-rendered scene.

### Step 2b — Upload artifacts to canopy-web (auto, every iteration)

Immediately after render, BEFORE the judges run, generate the per-iteration
HTML deck and upload it to canopy-web so every downstream consumer has a
hosted URL to reference. This step exists so the orchestrator never has to
do a one-off upload at surface-time, and so surfaced findings can include
hosted links the user can open from any device (per the pause-policy
artifact-link contract in `agents/ddd.md`).

```bash
# Generate the deck for this iteration. Same generator
# /canopy:walkthrough uses; scene_index + scene_total + scenes_run +
# scene_filter all flow through and the generator emits id="scene-<N>"
# anchors on every scene slide for deep-linking.
GEN="$DDD_REPO/scripts/walkthrough/generate_presentation.py"
ITER_DECK="<run_dir>/iter${state.iteration}_deck.html"
python3 "$GEN" \
  --input "<run_dir>/walkthrough-run-data.json" \
  --output "$ITER_DECK"

# Upload to canopy-web via /canopy:walkthrough-share's upload script.
# --public mints a share token so the URL works for anyone with the link
# (the user reading the surfaced finding on their phone). If you need
# dimagi-OAuth-gated only, drop --public.
#
# --run-id / --narrative-slug / --role group this artifact under its DDD run so it
# packages in canopy-web's /ddd views. Pass state.run_id and state.feature; the
# per-iteration deck is role=deck, the clip is role=clip.
UPLOAD="$DDD_REPO/scripts/walkthrough-share/upload.py"
DECK_URL=$(python3 "$UPLOAD" "$ITER_DECK" \
  --title "<unified_spec.name> iter${state.iteration}" \
  --run-id "<state.run_id>" --narrative-slug "<state.feature>" --role deck \
  --public 2>&1 | grep -oE 'https://[^ ]*' | tail -1)
```

If the recorded mp4 exists in the run dir, upload that too — and attach the
**companion links** the `/w/<id>` viewer renders so someone watching the clip
can act on it: jump back to the narrative, open the still-frame deck, and click
into the app pages the demo visited.

- `--narrative-url` — the narrative-review URL the gate stamped on
  `state.narrative_review_url` ("Back to the narrative").
- `--companion-url "$DECK_URL"` — the still-frame deck uploaded just above
  (labelled "Still-frame walkthrough" automatically for a video).
- `--spec "<unified_spec>"` — derives one "Explore in the app" reference link
  per scene `url` (label = scene title, deduped). The clip's destinations,
  clickable and live.

```bash
ITER_CLIP="<run_dir>/iter${state.iteration}_clip.mp4"  # if recorded
if [ -f "$ITER_CLIP" ]; then
  NARRATIVE_URL=$(python3 -c "from scripts.ddd.runstate import load; print(load('$run_id').narrative_review_url or '')")
  CLIP_ARGS=( "$ITER_CLIP" --public
    --title "<unified_spec.name> iter${state.iteration} (video)"
    --run-id "<state.run_id>" --narrative-slug "<state.feature>" --role clip
    --spec "<unified_spec>" )
  [ -n "$DECK_URL" ] && CLIP_ARGS+=( --companion-url "$DECK_URL" )
  [ -n "$NARRATIVE_URL" ] && CLIP_ARGS+=( --narrative-url "$NARRATIVE_URL" )
  CLIP_URL=$(python3 "$UPLOAD" "${CLIP_ARGS[@]}" 2>&1 | grep -oE 'https://[^ ]*' | tail -1)
fi
```

Stamp the URLs onto `run_state.yaml` so every downstream step (judges,
surfaced findings, the digest) can read them without re-running the upload:

```python
from scripts.ddd.runstate import load, save
state = load(run_id)
state.iteration_decks[state.iteration] = DECK_URL
if CLIP_URL:
    state.iteration_clips[state.iteration] = CLIP_URL
save(state)
```

**On upload failure:** log the failure to `<run_dir>/upload-errors.md` with
the iteration number and reason, leave the `iteration_decks` entry unset,
and CONTINUE to the judge step. The judges still score from the local
PNGs; the orchestrator's surface step will then fall back to a verbal
description per the artifact-link-or-verbal-description rule in
`agents/ddd.md`. **NEVER** fall back to `file://` paths.

**Deep-linking a scene:** consumers append `#scene-<N>` to the hosted
deck URL, where N is the original spec scene index. Example:
`<DECK_URL>#scene-2`. The deck generator emits stable anchors.

### Step 3 — Judge (parallel dispatch)

Dispatch **both judges simultaneously** — they are independent and can run in
parallel:

**3a. Concept judge** — invoke `ddd-concept-eval` (via Skill tool or
`/canopy:ddd-concept-eval`) with:
- `run_dir`: `<ddd_dir>/runs/<run_id>/`
- `unified_spec_path`: `<unified_spec>`
- `why_brief_path`: `<why_brief>`

Outputs: `verdict-concept.yaml` + `design_findings.json` inside the run dir.

**3b. User-artifact judge** — invoke `canopy:visual-judge` (via Skill tool)
over the rendered screenshots + page text, with `audience="feature user"`:

```python
Skill('canopy:visual-judge', args={
    'screenshot_path': '<run_dir>/scene_<N>.png',   # per scene, or the summary scene
    'page_text': '<captured page text from scene_<N>_page_text.json>',
    'rubric': {
        'name': 'user-artifact',
        'default_score': 3,
        'overall_rule': 'lowest',
        'dimensions': [
            {
                'id': 'task_completion',
                'label': 'Task completion',
                'weight': 0.40,
                'anchor': {
                    '5': 'Feature user can complete the target task without help, first try.',
                    '4': 'Task completable; one minor friction point. Name it.',
                    '3': 'Task completable with some trial-and-error. (DEFAULT)',
                    '2': 'Task requires assistance or a workaround.',
                    '1': 'Task cannot be completed — blocker present.',
                },
                'deduction_rules': [
                    'Broken flow that stops task mid-way: max 1',
                    'Required field unlabelled or missing: max 2',
                ],
            },
            {
                'id': 'clarity',
                'label': 'UI clarity for target user',
                'weight': 0.35,
                'anchor': {
                    '5': 'Every label, CTA, and state self-explains to a non-technical user.',
                    '4': 'Clear; one label or affordance could be sharper. Name it.',
                    '3': 'Understandable with a moment of thought. (DEFAULT)',
                    '2': 'At least one element confuses the target user.',
                    '1': 'Core action is hidden or mislabelled.',
                },
                'deduction_rules': [
                    'Jargon visible to non-technical users: max 2',
                ],
            },
            {
                'id': 'trust',
                'label': 'Trust / data confidence',
                'weight': 0.25,
                'anchor': {
                    '5': 'Numbers, sources, and recency are unambiguous; user trusts the output.',
                    '4': 'High trust; one data-provenance signal missing. Name it.',
                    '3': 'Reasonable trust; user may wonder about freshness. (DEFAULT)',
                    '2': 'Data looks stale or sourcing is unclear.',
                    '1': 'Outputs appear fabricated or internally inconsistent.',
                },
                'deduction_rules': [
                    'Placeholder / test data visible: max 2',
                ],
            },
        ],
    },
    'context': {
        'audience': {
            'name': 'feature user',
            'decision': 'deciding whether this feature solves their day-to-day problem',
        },
        'domain': '<unified_spec.name>',
    },
})
```

Collect the verdict object and write it as `verdict-user.yaml` in the run dir.

**Per-finding `fix_kind` on user-artifact findings.** For each dimension that
scored ≤ 3, the visual-judge verdict carries a `fix_recommendation`. Add a
`fix_kind` tag alongside it so the orchestrator can decide auto-apply vs ask
without re-parsing prose. Same vocabulary as `ddd-concept-eval`:

- `mechanical` — your recommendation names ONE concrete change (add a picker,
  rename a label, fix a URL). The orchestrator can apply via Edit + PR + deploy.
- `options` — recommendation lists 2+ paths and you couldn't pick. Smell:
  contains "Alternative:", "or", "could also". Requires user pick.
- `redesign` — underlying idea needs rethinking; no single fix would address it.

When in doubt, prefer `options` over `mechanical` — a wrongly auto-applied
finding is worse than one extra prompt.

The user-artifact verdict YAML carries these inside per-dimension entries:

```yaml
dimensions:
  task_completion:
    score: 2
    weight: 0.40
    justification: "Ambiguous rows offer only Skip — no inline disambiguation..."
    fix_recommendation: "Add an inline LGA picker per ambiguous row, populated from candidate list."
    fix_kind: mechanical
```

For dimensions that scored ≥ 4 (no finding emitted), `fix_recommendation` and
`fix_kind` are omitted.

### Step 4 — Assemble + convergence

Call `run_pipeline.assemble_run_state` to merge both verdict paths and findings
into `run_state.yaml`:

```python
from scripts.ddd.run_pipeline import assemble_run_state, compute_convergence
from scripts.ddd.runstate import load, save

state = load(run_id)
state = assemble_run_state(
    state,
    concept_verdict=<loaded concept verdict>,
    user_verdict=<loaded user verdict>,
    findings=<merged findings from design_findings.json>,
    concept_path="<run_dir>/verdict-concept.yaml",
    user_path="<run_dir>/verdict-user.yaml",
)

# Scene-filter metadata: read from the walkthrough sidecar and stamp it
# onto state. assemble_run_state preserves unknown keys, so a simple
# attribute set is fine. If your runstate model is stricter, add these as
# top-level fields on RunState.
import json
sidecar = json.load(open(f"{run_dir}/walkthrough-run-data.json"))
state.scenes_run = sidecar.get("scenes_run")          # e.g. [2] or [1,2,3,4,5]
state.scene_filter = sidecar.get("scene_filter")      # e.g. "2" or null
save(state)

converged = compute_convergence(concept_verdict, user_verdict)
```

**Upload gate.** `state.scene_filter is not None` means this is a
partial run — `/canopy:ddd-upload` MUST refuse to upload it. A
feature is only uploadable when convergence has been demonstrated
against the full spec.

### Step 5 — Report + auto_iterate signal

Before printing the report, compute the **auto_iterate signal** so the
orchestrator (and the human reader) knows whether the next iteration can
proceed without user input.

```python
# Aggregate findings from BOTH sources (concept design_findings + user-artifact dimension findings)
all_findings = []
for f in findings:                                    # design_findings.json
    all_findings.append({"route": f["route"], "fix_kind": f.get("fix_kind", "options")})
for dim_id, d in user_verdict.dimensions.items():     # user-artifact per-dimension
    if d.get("fix_kind"):
        all_findings.append({"route": "PRODUCT", "fix_kind": d["fix_kind"]})

# Decide the next action.
# Order of precedence: done > concept_change > partial_filtered > max_iter > continue > stop_unclear.
MAX_ITERATIONS = 3
non_defer = [f for f in all_findings if f["route"] != "DEFER"]
unclear = [f for f in non_defer if f["fix_kind"] in ("options", "redesign")]

if converged and not state.scene_filter:
    auto_iterate_next_action = "stop_done"
    reason = "Both judges passed full spec — ready for promotion."
elif converged and state.scene_filter:
    auto_iterate_next_action = "stop_partial"
    reason = "Both judges passed the filtered scope. Drop --scene and re-fire for full-spec promotion."
elif any(f["route"] == "CONCEPT" and f["fix_kind"] == "redesign" for f in non_defer):
    auto_iterate_next_action = "stop_concept_change"
    reason = "Concept-change finding present — fix requires user judgment on direction."
elif unclear:
    auto_iterate_next_action = "stop_unclear"
    reason = f"{len(unclear)} finding(s) with fix_kind='options' or 'redesign' — need user pick."
elif state.iteration >= MAX_ITERATIONS - 1:           # 0-indexed; next iter would be 3
    auto_iterate_next_action = "stop_max_iter"
    reason = f"Max iterations ({MAX_ITERATIONS}) would be exceeded by next iteration."
else:
    auto_iterate_next_action = "continue"
    reason = f"All non-DEFER findings are fix_kind='mechanical'. Orchestrator can apply and re-fire."
```

Stamp `auto_iterate_next_action` and `auto_iterate_reason` onto run_state
(both are optional fields on RunState — set them after save() or extend the
model). Then print the summary:

```
DDD Run — <run_id>
══════════════════════════════════════
  Spec: <unified_spec>
  Scope: --scene <selector> → rendered scenes <indices> of <total>      # only if filtered
  Run dir: <run_dir>
  Hosted deck (iter <N>): <DECK_URL>                                    # NEW — from Step 2b
  Hosted clip (iter <N>): <CLIP_URL>                                    # NEW — only if recorded

  Concept judge:       <concept overall_score>/5  (<verdict>)
  User-artifact judge: <user overall_score>/5     (<verdict>)

  Convergence (filtered): YES | NO  (threshold: 4.0)                    # "filtered" tag if partial

  Auto-iterate: <action>  (<reason>)                                    # NEW

  Top findings (<N> total):
    [PRODUCT mechanical]  Scene N: <detail>     <DECK_URL>#scene-<N>    # deep-link per finding
    [CONCEPT options]     Scene M: <detail>     <DECK_URL>#scene-<M>
    [RESEARCH mechanical] Scene K: <detail>     <DECK_URL>#scene-<K>
    [DEFER ]              Scene J: <detail>     <DECK_URL>#scene-<J>
    ...

  run_state.yaml updated → phase: judged
```

Each finding's deep-link uses the hosted deck URL from Step 2b plus the
`#scene-<N>` anchor for the scene the finding is about. If Step 2b's
upload failed (no entry in `state.iteration_decks[state.iteration]`),
drop the deep-link column and print a one-line note above the findings
table explaining the upload failure — never substitute a `file://` path.

The per-finding tag in the listing is `[<route> <fix_kind>]` so the reader
can see at a glance which findings the orchestrator will auto-apply
(`mechanical`) vs which need attention (`options`/`redesign`/DEFER).

**Tail messages by `auto_iterate_next_action`:**

- `stop_done` — "Both judges passed. Run is converged — proceed to promotion."
- `stop_partial` — "Filtered scope passed. Drop `--scene` and re-fire for promotion."
- `stop_concept_change` — "Concept-change finding present — surface to user via canopy-web review surface."
- `stop_unclear` — "Findings with `options`/`redesign` fix_kind block auto-iteration. List them and ask the user to pick or redesign."
- `stop_max_iter` — "Max iterations reached. Stop and surface remaining findings."
- `continue` — "Orchestrator can apply mechanical fixes per finding and re-fire `/canopy:ddd-run` on the same scope."

## Output files

| File | Producer | Notes |
|------|----------|-------|
| `<run_dir>/verdict-concept.yaml` | ddd-concept-eval | Concept judge verdict |
| `<run_dir>/design_findings.json` | ddd-concept-eval | Tagged design findings |
| `<run_dir>/verdict-user.yaml` | canopy:visual-judge (user-artifact) | User-artifact judge verdict |
| `<run_dir>/run_state.yaml` | assemble_run_state + save | phase=judged, verdict paths, findings |
