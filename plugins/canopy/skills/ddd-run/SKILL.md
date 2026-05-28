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

## Procedure

### Step 1 — Gate: spec QA

Before rendering, verify the spec is structurally sound:

```bash
python -m scripts.ddd.spec_qa <unified_spec>
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

All output lands in the run directory (`<ddd_dir>/runs/<run_id>/`).

> **Live labs note:** For live Connect Labs features, the render step also
> requires the connect-labs recorder rig, a freshness guard (confirming the
> deployed code is current), and a seeded demo.  Those are wired in the
> rooftop run — not here.  For dry runs and unit tests, the render step is
> exercised separately.

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
save(state)

converged = compute_convergence(concept_verdict, user_verdict)
```

### Step 5 — Report

Print a summary:

```
DDD Run — <run_id>
══════════════════════════════════════
  Spec: <unified_spec>
  Run dir: <run_dir>

  Concept judge:       <concept overall_score>/5  (<verdict>)
  User-artifact judge: <user overall_score>/5     (<verdict>)

  Convergence: YES | NO  (threshold: 4.0)

  Top findings (<N> total):
    [PRODUCT]  Scene N: <detail>
    [CONCEPT]  Scene M: <detail>
    ...

  run_state.yaml updated → phase: judged
```

If converged=YES, tell the user:
```
Both judges passed. Run is converged — proceed to promotion or human review.
```

If converged=NO, tell the user:
```
Not yet converged (<which judge(s)> below threshold or blocked).
Max iterations: 3.  Current iteration: <state.iteration>.
Recommend: address top findings and re-run /canopy:ddd-run.
```

## Output files

| File | Producer | Notes |
|------|----------|-------|
| `<run_dir>/verdict-concept.yaml` | ddd-concept-eval | Concept judge verdict |
| `<run_dir>/design_findings.json` | ddd-concept-eval | Tagged design findings |
| `<run_dir>/verdict-user.yaml` | canopy:visual-judge (user-artifact) | User-artifact judge verdict |
| `<run_dir>/run_state.yaml` | assemble_run_state + save | phase=judged, verdict paths, findings |
