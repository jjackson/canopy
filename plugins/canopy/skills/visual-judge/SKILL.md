---
name: visual-judge
description: |
  Score a captured screenshot against a caller-provided rubric using the
  Tough Judge methodology — adversarial listing first, conservative scoring
  from a 3/5 default, projector-test gate. Used by canopy:walkthrough for
  per-scene scoring and by ACE Phase 6 polish-eval for visual judgment.
  Use when asked to "judge a screenshot", "visual eval", or "tough judge".
---

# Visual Judge

Stand-alone scoring of a captured screenshot against a caller-provided
rubric. Implements the **Tough Judge methodology** — adversarial-first,
score-from-3 default, projector-test gate, calibration prior — that
canopy:walkthrough's scene loop used to inline. Extracted in canopy
v0.2.79 so the same judge can be reused by:

- **`canopy:walkthrough`** — once per captured scene (its 5-dim rubric:
  Content / App Page / Screenshot / Slide / Demo Readiness)
- **ACE `synthetic-workflow-polish-eval`** — once per polished workflow
  render (its 2-dim rubric: Visual Hierarchy / Brand Fit, alongside its
  text-based dimensions)
- **Future: any eval that needs visual judgment of a captured page**

The methodology is the durable part — adversarial-listing-before-scoring,
score-from-3-default, calibration prior, projector test, blocking rules.
Per-rubric dimensions are caller-provided so this skill stays general.

## Invocation

```
Skill('canopy:visual-judge', args={
  screenshot_path: '/abs/path/to/scene_3.png',
  page_text:       '<optional, output of `$B text` for anchoring>',
  rubric:          { ... see below ... },
  context:         { ... optional, see below ... },
})
```

Returns a verdict object (see `## Output verdict shape`).

## Inputs

### `screenshot_path` (required)

Absolute path to a PNG. The skill reads it via the Read tool so the
captured image is in the judge's context window during scoring.

### `page_text` (optional but strongly recommended)

The output of `$B text` (or equivalent) for the page that was screenshotted.
Without it, dimensions that cite "exact text" can't be scored faithfully —
e.g. "quote the worst sentence verbatim" only works against text the judge
can read. The walkthrough loop captures this; ACE evals capture it via
`browse text` after `browse goto`.

### `rubric` (required)

Caller-provided rubric YAML/object:

```yaml
name: <rubric name, e.g. "walkthrough" or "synthetic-polish">
default_score: 3        # the start-from default (3/5 by Tough Judge convention)
overall_rule: lowest    # or "weighted-mean"; "lowest" is canon for walkthrough
dimensions:
  - id: visual_hierarchy
    label: "Visual Hierarchy"
    weight: 0.40        # required; weights sum to 1.0
    anchor:
      "5": "World-class. Hero KPI prominent, perfect type scale, clear primary/secondary."
      "4": "Strong, with one designer-polish thing left to do. Name the thing."
      "3": "Functional. Ships. Nothing embarrassing, nothing delightful. (DEFAULT)"
      "2": "Visible problem a careful viewer catches: cramped spacing, etc."
      "1": "Damages credibility. Misaligned, unstyled, broken."
    deduction_rules:           # optional; per-dimension hard-caps
      - "Demo data artifacts ('Untitled', 'test-user') visible: max 2"
      - "Empty state dominating frame: max 3"

  - id: brand_fit
    label: "Brand fit"
    weight: 0.20
    anchor:
      "5": "..."
      ...
```

**Required fields per dimension:** `id`, `label`, `weight`, `anchor`.
**Optional:** `deduction_rules` (per-dimension hard-deduct triggers).

**Default score (3/5):** the calibration prior is "every dimension starts
at 3 — every step up earned with specific evidence, every step down
reflects a specific problem." Override only with a documented reason.

**Overall rule:** `lowest` (Tough Judge canon — weakest-link scoring,
walkthrough-style) or `weighted-mean` (more permissive — useful when
dimensions are independent).

### `context` (optional)

Caller-provided context that shapes the adversarial pass:

```yaml
audience:
  name: "skeptical CEO of a Fortune 500"
  decision: "deciding whether to adopt your product"
competitors: ["Linear", "Notion", "Slack", "Vercel", "Superhuman"]
projector_test_phrasing: |
  "Would you put this slide on a projector at an all-hands tomorrow,
  to your most demanding stakeholder, without ANY verbal caveats?"
narrative_anchors:                 # optional; specific claims this judgment can verify
  - "the headline panel must show ≥3 named FLWs with archetype labels"
  - "Dinesh's coaching arc must be visually called out"
domain: "turmeric market survey"   # informs brand-fit + content judgment
```

When omitted, defaults are walkthrough-flavored (CEO/Linear/Notion/etc.,
projector test as quoted above).

## Process — Tough Judge methodology

You are the harshest reviewer this product will ever face. Your job is
to find what's wrong, not feel good about what's right. If you're
scoring generously, you're scoring wrong.

**Calibration prior:** you are biased upward, especially if you built
or modified the thing being judged. Don't mechanically deduct —
**justify every 4 or 5 in one sentence a skeptical stranger would
accept.** If the justification reads as "it works" or "it's clean,"
the score isn't a 4 — that's a 3.

### Phase 1: Adversarial listing (MANDATORY before any scoring)

Read the screenshot (Read tool on `screenshot_path`) and the
`page_text` if provided. Then write three lists, in this order:

1. **Three most embarrassing things on this view** if you had to pause
   and explain them to `<context.audience>`. Be specific. Quote exact
   text from `page_text`, name exact UI elements visible in the
   screenshot. If you can't find three, you haven't looked hard enough.
   Common things to check:
   - Demo data artifacts (`Untitled`, duplicate titles, `test-user`,
     placeholder avatars)
   - Empty states dominating the frame
   - Error or warning banners visible
   - Feature gaps the audience would immediately ask about
   - Visual issues (low contrast, cramped spacing, inconsistent icon
     sizes)
   - Claimed-but-not-shown behavior (narrative says "streaming" but
     nothing streams)

2. **Three ways a competitor does this better.** Pick from
   `<context.competitors>` (or the walkthrough default list:
   Linear/Notion/Slack/Vercel/Height/Superhuman). Describe concretely
   what they do that this view doesn't. If you cannot name three,
   you are not thinking adversarially enough — look again.

3. **The binary projector test.** Use `<context.projector_test_phrasing>`
   verbatim, answer YES or NO. This answer is a hard gate on any
   "demo readiness" / "shippable" dimension below.

Output these three lists as a block. ONLY THEN proceed to scoring.

### Phase 2: Score each dimension, starting from `rubric.default_score`

For each dimension in `rubric.dimensions`:

- Apply the `anchor` definitions verbatim — don't paraphrase.
- Default to `default_score` (3 typically). Move up or down from the
  default with specific evidence.
- Apply per-dimension `deduction_rules` (if any) as HARD caps:
  rule fires → score caps at the rule's `max`, regardless of other
  evidence.
- For every score ≥ 4, write a one-sentence justification a skeptical
  stranger would accept.
- For every score ≤ 2, write a one-sentence reason citing a specific
  observable problem.

Computed `overall`:
- `rubric.overall_rule == "lowest"` → minimum dimension score
- `rubric.overall_rule == "weighted-mean"` → sum(dim.score * dim.weight)

### Phase 3: Cross-check (sanity floor)

Before emitting the verdict, check these sanity rules:

- **If ANY of your top-3 embarrassing things is unfixed in the
  screenshot, any "demo readiness" dimension cannot exceed 3.** No
  exceptions.
- **If the projector test is NO, any "demo readiness" dimension cannot
  exceed 3.**
- **If a competitor does it obviously better in all 3 named ways, the
  "app page quality" / "visual hierarchy" / equivalent dimension cannot
  exceed 3.**
- **Every 4 or 5 needs a one-sentence justification a stranger would
  accept.** "It works" / "it's clean" is not a 4 — that's a 3. Revise
  down if you can't name what earns the step up.

If a sanity rule binds and the dimension score has to drop, do it
explicitly and note "(sanity floor: <rule>)" in the dimension's
justification.

### Blocking rules (caller may opt in)

The walkthrough loop applies these blocking rules; other callers may
opt in by passing `context.blocking_rules: ["demo_readiness_low",
"narrative_falsified"]`:

1. **`demo_readiness_low`** — if any scored dimension labeled
   "demo readiness" (case-insensitive) lands ≤ 2, stop and tell the
   caller. Don't silently log it.
2. **`narrative_falsified`** — if the page contradicts a
   `context.narrative_anchors` claim, stop. The premise is wrong, not
   just the polish.

When opted-in and either fires, return a verdict with
`verdict: "blocked"` and `blocking_reason: <which rule>` instead of
the normal scored verdict.

## Output verdict shape

```yaml
schema_version: 1
rubric_name: <rubric.name>
ran_at: <ISO timestamp>
screenshot_path: <input>

# Phase 1 outputs
adversarial:
  embarrassing:
    - "verbatim quote / specific UI description"
    - "..."
    - "..."
  competitors_better:
    - { product: "Linear", what: "specific thing they do" }
    - { product: "Notion", what: "..." }
    - { product: "Superhuman", what: "..." }
  projector_test: YES | NO
  projector_test_reason: <one-sentence>

# Phase 2 outputs
dimensions:
  visual_hierarchy: { score: 4, weight: 0.40, justification: "..." }
  brand_fit:        { score: 3, weight: 0.20, justification: "..." }
  ...

overall_score: <number>
overall_rule: lowest | weighted-mean

# Phase 3 outputs (sanity floors that bound)
sanity_floors_applied:
  - { dimension: "visual_hierarchy", rule: "competitor_dominance_3", from: 4, to: 3 }

verdict: pass | warn | fail | blocked
blocking_reason: <when verdict==blocked> demo_readiness_low | narrative_falsified

fix_recommendation: |
  Concrete fix description. [CODE | SPEC | DATA | INFRA] tag.
```

## Calibration target

The methodology itself is calibrated against the walkthrough corpus
(canopy `evals/walkthrough/fixtures/` — defects with known severity
scores). When `canopy:walkthrough-eval` runs against fixtures, the
visual-judge dispatch should produce ground-truth-aligned scores. If
detection rate drops below 80% or inter-run variance rises above 0.5,
fix the methodology here, not in caller rubrics.

Per-rubric calibration (the `rubric` itself) is the caller's
responsibility — see `skills/eval-calibration/` in canopy or the
equivalent doc in the consuming repo.

## Why this lives in canopy

The Tough Judge methodology was authored for canopy:walkthrough but
is genuinely general — any eval that needs visual judgment of a
captured page benefits from the same adversarial-first + score-from-3
discipline. Embedding it inside walkthrough's scene loop forced
copy-paste for every other vision-judging eval. canopy is the right
home: it's the plugin that owns the methodology, the eval-fixture
corpus, and the calibration doc.

## Change Log

| Date | Change | Author |
|---|---|---|
| 2026-05-07 | Initial extraction from canopy:walkthrough Phase 1–4 inline scoring. Methodology preserved verbatim; per-rubric dimensions parameterized via the `rubric` input. canopy:walkthrough now dispatches this skill per scene; ACE polish-eval consumes it for visual dimensions. | canopy team |
