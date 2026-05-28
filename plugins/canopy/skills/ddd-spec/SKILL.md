---
name: ddd-spec
description: |
  Author a unified spec (docs/walkthroughs/<feature>.yaml) from a validated
  why_brief.yaml. Each spine item becomes one or more scenes with concept_claim,
  provenance, and design_intent. The output is simultaneously a design doc and a
  runnable canopy walkthrough spec. Loops until
  scripts.ddd.validate unified_spec passes. Use when asked to
  "write the spec", "author the unified spec", or after ddd-why-qa passes.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# DDD Unified Spec

Author a `docs/walkthroughs/<feature>.yaml` that is simultaneously:
1. The **design doc** — every scene asserts a testable concept_claim backed by a
   spine item (provenance).
2. A **runnable canopy walkthrough spec** — keys `name`, `narrative`, `base_url`,
   `auth`, `personas`, `scenes` conform exactly to the canopy walkthrough engine
   so it can be played directly by `/canopy:walkthrough`.

The unified spec is the linchpin artifact of the DDD v2 loop.  It is authored
FROM the grounded `why_brief.yaml` produced by Phase 0 (ddd-why-brief + ddd-why-qa).

## Inputs

- **`why_brief_path`** — path to the validated `why_brief.yaml`.
- **`feature`** — short slug used in the output filename and `name` field.
- **`base_url`** — the URL of the live environment to walk through.
- **`run_dir`** — directory to write the spec (default: `docs/walkthroughs/`).

## Procedure

### Step 1 — Read why_brief.yaml

```bash
cat <why_brief_path>
```

Parse the why_brief.  Note:
- `feature` — becomes the spec `name` and filename slug.
- `problem` — seeds the spec `narrative`.
- `spine` — each `SpineItem` becomes one or more scenes; the item's `id` becomes
  the scene `provenance`.
- `gaps` — surface any DECISION gaps to the user before proceeding (they may
  affect design_intent choices).

### Step 2 — Define personas

From the feature context, define 1–3 personas.  Each persona must have:
- `name` — a real first name (e.g. "Alice").
- `role` — the actor's role in the workflow (e.g. "Program Manager").
- `color` — a hex color that will appear in the walkthrough UI (e.g. `"#3B82F6"`).
- `intro` — one sentence describing who this persona is and their goal.

Every scene's `persona` field must be a key that exists in this `personas` dict.

### Step 3 — Draft scenes, one or more per spine item

For each SpineItem in the why_brief spine (in order), author one or more scenes.
Each scene must include:

**Canopy walkthrough keys (required by the walkthrough engine):**
- `persona` — must be a key in the `personas` dict.
- `title` — a short, action-oriented title for the scene (e.g. "Submit audit form").
- `show` — concrete, imperative browser actions the walkthrough will execute
  (e.g. `"navigate to /audit/new, fill the 'observation' field, click Submit"`).

**DDD-specific keys (required by ddd-spec-qa gate):**
- `concept_claim` — one assertive sentence describing what the product does in this
  scene AND why it matters.  This claim must be:
  - **Non-empty** — never leave it blank or whitespace.
  - **Falsifiable** — a skeptical observer must be able to confirm or refute it by
    watching the walkthrough.  Do NOT use: "world-class", "seamless", "powerful",
    "robust", "best-in-class", "cutting-edge", or similar marketing language.
    DO write: a specific action and its observable result, optionally with a
    measurable outcome (e.g. "within 2 seconds", "without leaving the page").
  - **At least 5 words** — a claim shorter than 5 words is too vague to be testable.
    Subtle vacuousness (e.g. articulate-but-empty fluff) is caught later by the LLM
    concept judge (/ddd-concept-eval).
- `provenance` — the `SpineItem.id` this scene demonstrates (e.g. `"S1"`).  Must
  match an existing spine id in the linked why_brief.
- `design_intent` (optional but strongly recommended) — the design decision or
  hypothesis under test in this scene.  What are we betting on?
- **`features` (required by ddd-spec-qa — ≥1 per scene)** — a list of concrete
  buildable units.  Each feature must have:
  - `id` — a short unique slug (e.g. `"boundary-draw"`).
  - `description` — what to implement, in one sentence.  Must be concrete enough
    that an engineer can open a ticket from it.
  - `verify` — a **runnable validation** (≥3 words) — a real API assertion, UI
    state check, or test command.  Vague phrases like "check it works" will fail
    the `ddd-narrative-actionability-eval`.

**Good features vs vague features:**

```yaml
# GOOD — concrete buildable unit with a runnable verify
features:
  - id: task-filter-ui
    description: Status dropdown filter on the task list page (/tasks)
    verify: "Playwright: select 'Open' in Status dropdown, assert only open tasks visible"
  - id: task-filter-api
    description: "GET /tasks?status= filters tasks server-side by status enum"
    verify: "pytest: GET /tasks?status=open returns 200 with all tasks having status=open"

# BAD — vague, not runnable
features:
  - id: filtering
    description: Add filtering support
    verify: test it  # too short, not a real assertion
```

**`ddd-spec-qa` now requires ≥1 verifiable feature per scene.**  A scene with
`features: []` (or no `features` key) will fail spec-qa and block the gate.
The `ddd-narrative-actionability-eval` will additionally score whether the
narration (concept_claim + show) implies those features to a cold reader.

**Examples of falsifiable concept_claims:**
- "When a supervisor submits the audit form, the FLW receives a coaching task within 60 seconds"
- "Users can filter the task list by status and see only open tasks without a page reload"
- "The sampling engine selects buildings proportional to floor count and shows the sample on a map"

**Examples of non-falsifiable concept_claims (will fail ddd-spec-qa):**
- "A world-class seamless experience for field workers" — banned phrases (world-class, seamless)
- "Robust performance" — banned phrase, too short to be testable
- "Powerful filtering" — banned phrase

### Step 4 — Fill canopy walkthrough header keys

At the top level of the spec, include:

```yaml
name: <feature slug>
narrative: >-
  <1–2 sentences derived from why_brief.problem and the spine's logical arc.
  This is read aloud as the walkthrough introduction.>
base_url: <live environment URL, e.g. https://labs.connect.dimagi.com>
auth:
  type: session   # or omit if the walkthrough handles auth via browser cookies
why_brief: why_brief.yaml   # relative path from the spec file to the why_brief
personas:
  <persona_key>:
    name: ...
    role: ...
    color: ...
    intro: ...
scenes:
  - persona: ...
    title: ...
    show: ...
    concept_claim: ...
    provenance: ...
    design_intent: ...
    features:
      - id: <slug>
        description: <concrete buildable unit — what to implement>
        verify: <runnable validation — API assertion, UI state check, or test command>
```

The output file path is `<run_dir>/<feature>.yaml`.

### Step 5 — Write the spec file

Write the draft to `docs/walkthroughs/<feature>.yaml` (create the directory if
it doesn't exist).

### Step 6 — Validate and loop

Run the structural validator (it lives in the canopy repo; resolve `DDD_REPO` once
and reuse it for both commands in this step):

```bash
# scripts/ddd ships in the canopy repo, not the plugin cache — resolve it:
DDD_REPO="$HOME/emdash-projects/canopy"; [ -d "$DDD_REPO/scripts/ddd" ] || DDD_REPO="$HOME/.claude/plugins/marketplaces/canopy"
if [ ! -d "$DDD_REPO/scripts/ddd" ]; then echo "ERROR: scripts/ddd not found — run /canopy:update to sync the canopy checkout"; exit 1; fi
# pass the file arg as an absolute path (resolved before the cd):
SPEC_ABS="$(realpath docs/walkthroughs/<feature>.yaml)"
(cd "$DDD_REPO" && uv run python -m scripts.ddd.validate unified_spec "$SPEC_ABS")
```

If it exits non-zero, read each problem and fix the spec.  Re-run until the
validator exits 0.  After 3 fix attempts, surface the remaining errors to the
user rather than looping further.

Common fixes:
- `scene references undefined persona` → add the persona to `personas` or fix the
  scene's `persona` key.
- `provenance ... does not match any SpineItem.id` → update `provenance` to match
  the correct spine id from the why_brief.
- `why_brief declared but not resolvable` → check the relative path from the spec
  file to the why_brief file.
- `base_url: field required` → add `base_url` at the top level.

**Important:** after the validate pass, also run ddd-spec-qa (SP2.2) to catch
non-falsifiable concept_claims before the concept judge runs (reuse `DDD_REPO` from
above — it is already resolved):

```bash
(cd "$DDD_REPO" && uv run python -m scripts.ddd.spec_qa "$SPEC_ABS")
```

Fix any `concept_claim is not falsifiable` violations before proceeding.

### Step 7 — Confirm the spec remains a runnable walkthrough

Before reporting success, verify the spec still satisfies the canopy walkthrough
engine's minimum requirements:
- `name`, `narrative`, `base_url`, `personas`, `scenes` are all present.
- Every scene has `persona`, `title`, `show`.
- The spec can be parsed by `scripts.ddd.validate unified_spec` (run via the resolved `DDD_REPO` pattern from Step 6).

Do NOT remove any of these keys even if they seem redundant with the DDD fields.
The unified spec must remain playable by `/canopy:walkthrough`.

### Step 8 — Report

After both validators pass, print:

```
DDD Unified Spec — <feature>
══════════════════════════════════════

  Spine items: N → M scenes
  Personas: <list of persona names>
  Scenes:
    [S1] <scene title> — <concept_claim (first 60 chars)>... (N features)
    [S2] <scene title> — ... (N features)

  Output: docs/walkthroughs/<feature>.yaml
  Validator (structural): PASS
  Validator (spec_qa):    PASS

Next steps:
  1. /ddd-narrative-actionability-eval — LLM-as-judge: can a cold reader derive the
     declared features from the narration alone? (gate — must pass before review)
  2. /ddd-narrative-review — get the user's explicit approve/redraft on the story
     arc (the concept gate) before any rendering or building.
  3. /ddd-run — render, judge, and converge.
```

If there are DECISION gaps from the why_brief, list them explicitly so the user
can make those decisions before the concept judge runs.
