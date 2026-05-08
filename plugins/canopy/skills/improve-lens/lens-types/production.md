# Production Lens Runner

You are running canopy's **production lens** against a target project. Your job: identify producer-skill quality issues from eval verdicts and draft producer-prompt edits. The dispatcher will run sandbox-regen verification (re-dispatch the edited producer against same inputs, re-grade the new artifact) and ship PRs for human review.

## Status: skeleton (v1)

The descriptor and signal taxonomy are settled; the runner implements signal detection but defers the sandbox-regen verification wiring to a follow-up PR. v1 behavior:

1. Run signal detectors and identify findings (per the descriptor).
2. Draft proposals.
3. **Mark all proposals `verification: deferred`** — return them to the dispatcher with a note that v1 production lens drafts proposals but does not yet self-verify.
4. The dispatcher writes them to `~/.claude/canopy/proposals/` with `status: pending_verification` so they're queued for the future sandbox-regen runner without blocking on infrastructure that doesn't exist yet.

This keeps the production-lens descriptor + analyzer pattern in place so v2 can add sandbox-regen without redesigning the contract.

## Inputs (provided by the dispatcher)

Same as the judge lens runner — project path, run id, descriptor, evidence sources, drive root, max proposals.

## Process

### Step 1 — Walk the run's verdicts

Same as judge lens — list `runs/<run-id>/**/*-eval_verdict*.yaml`.

### Step 2 — Cross-model consensus probe (signal `consistent_warn_across_models`)

If the judge lens already ran on this run and wrote verdicts to `~/.claude/canopy/proposals/`, read those cross-model verdicts to avoid duplicating the probe. Otherwise dispatch the probe yourself (same template as judge lens Step 2).

Look for `auto_surfaced` concerns where the SAME concern appears in all 3 cross-model verdicts AND the original verdict. That's a real producer gap, not rubric ambiguity. Flag as **consistent_warn_across_models**.

### Step 3 — Low-score-low-variance probe (signal `low_score_low_variance`)

For each dimension where:
- mean score across 4 verdicts (original + 3 cross-model) ≤ 6
- stdev across the 4 verdicts < 0.5

Flag as **low_score_low_variance** — the artifact really has the issue, the rubric agreed across models, the producer needs to address it.

### Step 4 — Structural-gap attribution (signal `missing_section_recurring`)

If `structural_completeness` (or equivalent dimension) flagged a missing required section, identify which producer skill is supposed to write that section. Look up the producer's SKILL.md `## Process` section to confirm the prompt doesn't currently instruct the model to include it. Flag as **missing_section_recurring** with the specific section name + producer skill.

### Step 5 — Draft producer-prompt edits

For each finding, draft a candidate producer-prompt edit:

- **consistent_warn_across_models / low_score_low_variance**: add explicit instruction to the producer's `## Process` step that addresses the dimension's criteria. e.g. if `feasibility_headline_metrics` consistently scores low because Layer B verification claims defer model selection, add to PDD producer: "Step N: Layer B claims must name the implementing model + threshold + expected pass rate, OR explicitly defer to Phase 4 with named ownership."
- **missing_section_recurring**: add explicit instruction to include the missing section, with anchor text matching the rubric's expected structure.

Format:

```yaml
target_file: "skills/<producer-skill>/SKILL.md"
target_section: "## Process"
edit_type: text_replacement
old_text: |
  <exact substring, ≤ 50 lines>
new_text: |
  <replacement text>
rationale: |
  <why this edit addresses the eval finding>
```

### Step 6 — Return findings + proposals (deferred verification)

Return the same YAML shape as judge lens, with each proposal additionally marked:

```yaml
verification: deferred
verification_reason: "production lens v1 does not yet implement sandbox-regen; proposal queued for v2."
```

The dispatcher writes the proposal to `~/.claude/canopy/proposals/` with `status: pending_verification` and does NOT open a PR. Human can review the queued proposals via `~/.claude/canopy/proposals/` and manually validate them.

## v2 verification (not yet implemented)

When sandbox-regen lands:

1. Apply edit to producer SKILL.md in memory.
2. Read producer's input artifacts from `inputs-manifest.yaml` + upstream artifacts.
3. Dispatch a `general-purpose` Agent that runs the EDITED producer prompt against those inputs, writing output to `runs/<run-id>/8-closeout/eval-improve/sandbox/<producer>/<artifact>`.
4. Re-dispatch the matching `-eval` skill against the sandbox artifact.
5. Compare new verdict vs original — pass if targeted dimension improved AND no other dimension regressed > 0.5.
6. Open PR with comparison evidence; tag for human review (production lens never auto-merges per descriptor).

## Important notes

- **Producer changes affect every future run.** That's why production lens never auto-merges. Always human review.
- **Don't propose changes the judge lens should make.** If the issue is rubric ambiguity (high cross-model variance), refer to judge lens via `cross_lens_referral: judge`.
- **Inputs are contracts.** Don't propose edits that change the producer's declared `## Inputs` — those are read by the orchestrator and the artifact-manifest. Inputs changes need orchestrator coordination.
