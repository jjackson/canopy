---
name: ddd-concept-eval
description: |
  LLM-as-judge eval for a rendered walkthrough. Scores five weighted dimensions
  (concept_clarity .20, design_soundness .25, why_groundedness .20,
  claim_reality_coherence .15, motion_friction .20) using the rubric bundled with
  this skill. Gated by ddd-spec-qa — if QA fails, this eval is skipped.
  Per scene, dispatches canopy:visual-judge with the concept rubric and the scene's
  concept_claim / provenance / captured page text as anchors. Aggregates to a
  weakest-link overall_score. Collects design_findings[] tagged with PRODUCT /
  CONCEPT / RESEARCH / DEFER routes. Writes verdict-concept.yaml + design_findings.json.
  claim_reality_coherence findings are surfaced and scored but NEVER set verdict=blocked.
  Use when asked to "eval the concept", "score the walkthrough concept", or after
  ddd-spec-qa passes.
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash ~/emdash-projects/canopy/scripts/canopy-update-check.sh 2>/dev/null || true)
if [ -n "$_CANOPY_UPD" ]; then echo "$_CANOPY_UPD"; fi
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

## Calibration status

Provisional rubric; calibrate via a defect-creator analog after 3 real runs
(deferred per spec). Not yet calibrated.

# DDD Concept Eval

LLM-as-judge scoring of a rendered walkthrough (per-scene screenshots + captured
page text) against a 5-dimension concept rubric. Measures whether the **product
concept** is sound — not whether the video is pretty. Emits structured
`design_findings[]` that route to fixers.

**QA gate:** If ddd-spec-qa returned verdict: fail, skip this eval.

## Inputs

- **`run_dir`** — path to a rendered walkthrough run dir. Must contain:
  - `scene_<N>.png` screenshots for each scene
  - `scene_<N>_page_text.json` (captured page text from `$B text` — one file per scene)
  - `unified_spec.yaml` (or passed separately via `unified_spec_path`)
  - `why_brief.yaml` (or passed separately via `why_brief_path`)
- **`unified_spec_path`** — optional explicit path to `unified_spec.yaml` if not inside `run_dir`.
- **`why_brief_path`** — optional explicit path to `why_brief.yaml` if not inside `run_dir`.

## Procedure

### Step 0 — Check QA gate

Before scoring, verify ddd-spec-qa has passed for this spec (the script lives in
the canopy repo):

```bash
# scripts/ddd ships in the canopy repo, not the plugin cache — resolve it:
DDD_REPO="$HOME/emdash-projects/canopy"; [ -d "$DDD_REPO/scripts/ddd" ] || DDD_REPO="$HOME/.claude/plugins/marketplaces/canopy"
if [ ! -d "$DDD_REPO/scripts/ddd" ]; then echo "ERROR: scripts/ddd not found — run /canopy:update to sync the canopy checkout"; exit 1; fi
# pass the file arg as an absolute path (resolved before the cd):
SPEC_ABS="$(realpath <run_dir>/unified_spec.yaml)"
(cd "$DDD_REPO" && uv run python -m scripts.ddd.spec_qa "$SPEC_ABS")
```

If the exit code is non-zero (verdict: fail), stop immediately and tell the user:

```
ddd-concept-eval: BLOCKED — ddd-spec-qa must pass before concept eval.
  blocking_reason: <spec_qa blocking_reason>
  Fix the structural issues listed above, re-run /ddd-spec-qa, then retry /ddd-concept-eval.
```

Do not score a structurally broken spec.

### Step 1 — Load rubric and artifacts

Read the bundled rubric:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-concept-eval/rubric.yaml')"
```

Read the file at that path. Also read `unified_spec.yaml` and `why_brief.yaml`.
Build a lookup: `why_brief.spine[].id` → `{claim, rationale, evidence, status}`.

### Step 2 — Per-scene dispatch to canopy:visual-judge

For each scene in `unified_spec.yaml`:

1. Identify the screenshot path: `<run_dir>/scene_<N>.png` (or the path recorded in the run manifest).
2. Load the captured page text: `<run_dir>/scene_<N>_page_text.json`.
3. Build the `context` object for canopy:visual-judge:
   - `narrative_anchors`: [`scene.concept_claim`, `scene.provenance`, the matching why_brief spine rationale (if resolvable)]
   - `domain`: `unified_spec.name`
   - `audience.name`: "skeptical product reviewer who has read the why_brief"
   - `audience.decision`: "deciding whether the concept holds water"
   - Do NOT pass `blocking_rules` — claim_reality_coherence is non-blocking by spec.
4. Dispatch `canopy:visual-judge` with:
   - `screenshot_path`: the scene screenshot
   - `page_text`: the captured page text
   - `rubric`: the ddd-concept-eval rubric (from Step 1)
   - `context`: the context object from step 3

Collect the per-scene verdict object. Extract all dimension scores.

### Step 3 — Tag design_findings per scene

For each dimension score ≤ 3 in the per-scene visual-judge output, create a
`design_finding` entry:

```yaml
scene: <scene index or title>
dimension: <dim_id>
severity: high | medium | low   # high if score ≤ 1, medium if score == 2, low if score == 3
route: PRODUCT | CONCEPT | RESEARCH | DEFER
fix_kind: mechanical | options | redesign
detail: <copy the justification from the visual-judge dimension output>
fix_recommendation: <copy the fix_recommendation from visual-judge, or synthesize>
```

Route assignment rules:
- `concept_clarity` findings → CONCEPT
- `design_soundness` findings → **PRODUCT** if the fix changes how the product is *presented* without changing what it does (e.g. interaction wording, affordance labelling, flow ordering); → **CONCEPT** if fixing it requires changing *what the product does* (e.g. a core interaction is incoherent because the underlying idea is wrong)
- `why_groundedness` findings → RESEARCH (if provenance is missing) or CONCEPT (if the claim contradicts the why_brief)
- `claim_reality_coherence` findings → always DEFER (non-blocking; note discrepancy for later triage)
- `motion_friction` findings → PRODUCT

`fix_kind` assignment — set it based on the SHAPE of your fix_recommendation,
NOT on what feels right:

- **`mechanical`** — your fix_recommendation names ONE concrete change a
  reader could apply without choosing. Examples:
  - "Add an inline LGA picker on each ambiguous row, populated from the
    candidate list returned by resolve_many."
  - "Patch unified_spec.yaml feature `resolve-many-endpoint.verify` to
    reference the actual shipped URL: POST /labs/explorer/boundaries/resolve_many/."
  - "Rename the scene title from 'Dana sees the wards' to 'Dana confirms
    each ward before commit'."
  This is the COMMON case. Most well-tuned findings are mechanical.

- **`options`** — your fix_recommendation lists 2+ paths and you couldn't
  pick. Smell tests: contains "Alternative:", "or", "could also", "consider
  X or Y". Examples:
  - "Add a spine item with id `name-resolution-confirm`. Alternative: extend
    `area-selection` to cover bulk input and document the link."
  - "Either tighten the narration to match the 6/4 reality, or expand
    scene 2 into two beats — initial resolve, then disambiguation."
  These need a user pick. The orchestrator surfaces them.

- **`redesign`** — the underlying idea needs rethinking; no single change
  fixes it. Smell tests: the recommendation is itself a question, or it
  asks for a meeting/discussion/reconception. Examples:
  - "The concept of 'all wards must be matched before commit' may be wrong
    here — consider whether partial batches make sense."
  - "Rethink what 'matched' means in the context of programmatic ward sets."
  These surface as `concept_change` — never auto-apply.

When in doubt, prefer `options` over `mechanical`. A wrongly auto-applied
finding is much worse than one extra user prompt. The orchestrator's
auto-iterate loop only acts on `mechanical` findings; anything else stops
the loop and surfaces to the user.

**claim_reality_coherence findings are surfaced and scored but NEVER set verdict=blocked.**

### Step 4 — Aggregate overall score

Compute `overall_score` across ALL scenes via `overall_rule: lowest` (the minimum
dimension score across all scenes for the **four gating dimensions**:
`concept_clarity`, `design_soundness`, `why_groundedness`, and `motion_friction`).

`claim_reality_coherence` is EXCLUDED from the weakest-link overall_score, so it
can never drive verdict to warn/fail/blocked. It is advisory: it informs the human
at the pause point, it does not gate convergence. `claim_reality_coherence` scores
are STILL recorded per scene in the `dimensions{}` map and STILL generate
DEFER-routed `design_findings`, but they play no role in computing `overall_score`
or the final verdict.

### Step 5 — Compute verdict

| overall_score | verdict |
|---------------|---------|
| ≥ 4 | pass |
| 3 | warn |
| ≤ 2 | fail |

`verdict: "blocked"` is only set if Step 0 fired (QA gate failed). It is NOT set
for low claim_reality_coherence scores.

### Step 6 — Write outputs

Write two files to `<run_dir>/`:

**`verdict-concept.yaml`** (visual-judge verdict shape):

```yaml
schema_version: 1
rubric_name: ddd-concept-eval
ran_at: <ISO timestamp>
run_dir: <input>

dimensions:
  concept_clarity:          { score: N, weight: 0.20, justification: "..." }
  design_soundness:         { score: N, weight: 0.25, justification: "..." }
  why_groundedness:         { score: N, weight: 0.20, justification: "..." }
  claim_reality_coherence:  { score: N, weight: 0.15, justification: "...", blocking: false }
  motion_friction:          { score: N, weight: 0.20, justification: "..." }

overall_score: N
overall_rule: lowest

verdict: pass | warn | fail | blocked
blocking_reason: <null unless verdict==blocked>

fix_recommendation: |
  <Concrete fix description addressing the lowest-scoring dimensions.
   Tag: [PRODUCT] for interaction changes, [CONCEPT] for idea changes,
   [RESEARCH] for evidence gaps, [DEFER] for claim_reality_coherence gaps.>
```

**`design_findings.json`**:

```json
[
  {
    "scene": "<scene title or index>",
    "dimension": "<dim_id>",
    "severity": "high | medium | low",
    "route": "PRODUCT | CONCEPT | RESEARCH | DEFER",
    "detail": "<verbatim from visual-judge dimension justification>",
    "fix_recommendation": "<actionable fix>"
  }
]
```

### Step 7 — Report

Print a summary:

```
Concept Eval — <spec name>
══════════════════════════════════════
  Scenes evaluated: <N>

  concept_clarity:          N/5  — <one-line justification>
  design_soundness:         N/5  — <one-line justification>
  why_groundedness:         N/5  — <one-line justification>
  claim_reality_coherence:  N/5  — <one-line justification> [non-blocking]
  motion_friction:          N/5  — <one-line justification>
  ────────────────────────────────────
  Overall (lowest):         N/5

  Verdict: PASS | WARN | FAIL

  design_findings: <count> findings  (PRODUCT: N, CONCEPT: N, RESEARCH: N, DEFER: N)
  Outputs: <run_dir>/verdict-concept.yaml
           <run_dir>/design_findings.json
```

If verdict is `warn` or `fail`, print the `fix_recommendation`.

If verdict is `pass`, tell the user:

```
Concept looks sound. Next step: review design_findings for any PRODUCT/CONCEPT
route items worth addressing before promoting, then proceed with the run.
```

## Output verdict shape

```yaml
schema_version: 1
rubric_name: ddd-concept-eval
ran_at: <ISO timestamp>
dimensions:
  concept_clarity:          { score: <float>, weight: 0.20 }
  design_soundness:         { score: <float>, weight: 0.25 }
  why_groundedness:         { score: <float>, weight: 0.20 }
  claim_reality_coherence:  { score: <float>, weight: 0.15, blocking: false }
  motion_friction:          { score: <float>, weight: 0.20 }
overall_score: <float>
overall_rule: lowest
verdict: pass | warn | fail | blocked
blocking_reason: <string | null>
fix_recommendation: <string | null>
```
