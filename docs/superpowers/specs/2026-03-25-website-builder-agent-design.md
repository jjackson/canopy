# Website Builder Agent — Design Spec

**Date:** 2026-03-25
**Branch:** emdash/website-builder-72a
**Status:** APPROVED (design doc 9/10, CEO review clean, outside voice resolved)

## Summary

A Canopy plugin agent (`@website-builder`) that uses persistent memory to store
Dimagi-wide brand context and per-product knowledge, then orchestrates a pipeline
of existing Claude Code skills to generate, QA, and iterate on marketing websites.
Includes an evaluation framework for tracking quality over time.

Connect is the first customer. The wedge is one polished landing page.

## Architecture

### Agent Definition

File: `plugins/canopy/agents/website-builder.md`

The agent uses Claude Code's `memory: user` for Dimagi-wide brand context
(persists in `~/.claude/agent-memory/website-builder/`) and reads product-specific
context from a `context/` directory in the current working directory.

The agent's system prompt defines a multi-stage pipeline. Each stage invokes an
existing skill or performs inline analysis. Stages are sequential — output from
one feeds the next.

### Pipeline Stages (Phase 1: Core)

```
1. CONTEXT INGESTION
   Read: agent memory (brand) + ./context/ (product)
   Output: structured creative brief (markdown)

2. DESIGN SYSTEM
   Invoke: /design-consultation (or reuse existing DESIGN.md)
   Output: DESIGN.md in working directory

3. GENERATION
   Invoke: /frontend-design with creative brief + DESIGN.md
   Output: HTML/CSS/JS files in ./output/

4. QA
   Start local server, invoke /browse for screenshots
   Invoke /design-review on screenshots + source
   Output: screenshots + issue list

5. USER REVIEW
   Present screenshots + issues
   Accept user feedback
   Output: approve / revise / regenerate

6. ITERATION (if revise/regenerate)
   Apply feedback, loop back to step 3
   Max 5 cycles before forcing approval
```

### Pipeline Stages (Phase 2: Expansions)

Added after core pipeline works end-to-end:

- **Visual direction picker** — before step 3, generate 3 hero-section variants,
  user picks one. Reduces iteration cycles.
- **Content tone analyzer** — during step 1, analyze product copy tone (formal/casual,
  technical/accessible). Append tone profile to creative brief.
- **Responsive preview grid** — during step 4, screenshot at 1440px, 768px, 375px.
  Present all three to user.
- **Brand consistency scorer** — after step 3, check generated CSS against DESIGN.md
  for font/color deviations. Score < 7 triggers auto-fix.
- **Stakeholder slideshow** — after approval, invoke /walkthrough to generate
  presentation-ready HTML slideshow.

### Memory Model

```
~/.claude/agent-memory/website-builder/    (Dimagi-wide, memory: user)
├── MEMORY.md                              (auto-loaded, first 200 lines)
├── brand-guidelines.md                    (visual identity rules)
├── tone-of-voice.md                       (writing style)
└── approved-aesthetics.md                 (styles user has approved)

./context/                                 (product-specific, per working dir)
├── product-brief.md                       (what the product does)
├── value-propositions.md                  (key messaging)
├── target-audience.md                     (who we're talking to)
└── reference-materials/                   (2-pagers, decks, etc.)
```

The agent's MEMORY.md accumulates preferences over time: approved color palettes,
font choices, layout patterns, feedback patterns. This is what makes the 5th run
better than the 1st.

Product context lives in the working directory (not agent memory) so it can be
version-controlled and shared.

### Error Handling

Every stage has a defined failure mode:

| Stage | Failure | Action |
|-------|---------|--------|
| Context | No ./context/ dir | Error: "Create a context/ directory with product docs" |
| Context | Empty memory | Warning: "No brand context. Run setup or provide brand docs" |
| Design system | /design-consultation fails | Reuse existing DESIGN.md; error if none exists |
| Generation | /frontend-design fails | Retry once with simplified prompt; error on second fail |
| QA - server | Port unavailable | Use port 0 (OS-assigned) |
| QA - browse | Screenshot fails | Skip visual QA, present files directly with warning |
| QA - review | /design-review fails | Skip automated review, proceed to user review |
| Iteration | 5 cycles reached | Force user review with warning |

## Evaluation Framework

### Concept

Every generation run is a recorded eval case. Fixed context inputs + captured
outputs + automated scores = a dataset that shows whether the agent improves
over time.

### Directory Structure

```
evals/
├── connect/                           (product eval suite)
│   ├── context/                       (FIXED test inputs — don't change between runs)
│   │   ├── product-brief.md
│   │   ├── brand-guidelines.md
│   │   ├── tone-reference.md
│   │   └── reference-sites.md
│   ├── runs/                          (one dir per generation run)
│   │   └── YYYY-MM-DD-vNNN/
│   │       ├── input-prompt.md        (exact prompt sent to /frontend-design)
│   │       ├── design-system.md       (DESIGN.md used)
│   │       ├── output/                (generated HTML/CSS/JS)
│   │       ├── screenshots/           (desktop.png, tablet.png, mobile.png)
│   │       ├── scores.json            (automated quality scores)
│   │       └── human-review.md        (optional user notes)
│   ├── baseline.json                  (best scores to beat)
│   └── eval-history.json              (all scores over time)
```

### Scoring Dimensions (1-10 each)

1. **visual_quality** — Professional design quality. Scored by analyzing the
   screenshot: layout balance, typography hierarchy, whitespace, visual polish.
   The agent reads the screenshot and scores it against professional marketing
   site standards.

2. **brand_consistency** — Adherence to DESIGN.md. Scored by parsing CSS from
   generated HTML and comparing font-family, color hex values, and font-size
   values against DESIGN.md specifications. Mechanical check, not subjective.

3. **content_accuracy** — Product-specific content vs generic AI copy. Scored by
   checking how many product-specific terms, feature names, and value props from
   context/product-brief.md appear in the generated HTML text content. Higher
   count = higher score.

4. **responsiveness** — Works at all viewport widths. Scored by comparing desktop,
   tablet, and mobile screenshots for layout breakage, overflow, and readability.
   All three must look intentional, not broken.

5. **code_quality** — Valid HTML, no console errors, no broken resources. Scored
   by checking HTML validity, verifying all referenced resources exist, and
   checking for common issues (missing alt text, broken links, inline styles
   that should be in CSS).

### Composite Score

`overall = (visual_quality * 0.3) + (brand_consistency * 0.2) + (content_accuracy * 0.25) + (responsiveness * 0.15) + (code_quality * 0.1)`

Visual quality and content accuracy weighted highest — these are what stakeholders
notice. Code quality weighted lowest — important but not the differentiator.

### scores.json Format

```json
{
  "run_id": "2026-03-25-v001",
  "timestamp": "2026-03-25T16:00:00Z",
  "agent_version": "0.1.0",
  "dimensions": {
    "visual_quality": { "score": 7, "notes": "Good hierarchy, hero needs more impact" },
    "brand_consistency": { "score": 9, "notes": "All fonts match, one color deviation" },
    "content_accuracy": { "score": 8, "notes": "12/15 product terms found in output" },
    "responsiveness": { "score": 6, "notes": "Mobile nav overlaps hero text" },
    "code_quality": { "score": 8, "notes": "Valid HTML, 2 missing alt texts" }
  },
  "overall": 7.55,
  "context_hash": "abc123",
  "prompt_hash": "def456",
  "vs_baseline": "+0.5"
}
```

### Eval Commands

- `@website-builder eval connect` — Run full pipeline against fixed Connect
  context, score, save run, compare against baseline.
- `@website-builder eval connect --update-baseline` — Set current run as the
  new baseline (after human review confirms it's the best so far).
- `@website-builder eval connect --history` — Show score trends over time.
- `@website-builder eval connect --compare v001 v002` — Side-by-side comparison
  of two runs (screenshots + scores).

### Eval Workflow

```
1. Agent reads evals/connect/context/ (fixed inputs)
2. Runs full pipeline (context → design → generate → QA)
3. Saves outputs to evals/connect/runs/YYYY-MM-DD-vNNN/
4. Scores each dimension
5. Writes scores.json
6. Compares against evals/connect/baseline.json
7. Reports: "Overall: 7.55 (+0.5 vs baseline). Improved: visual_quality.
   Regressed: responsiveness."
8. Appends to evals/connect/eval-history.json
```

### Using Evals to Improve

The eval framework enables a tight improvement loop:

1. Run eval → see scores
2. Identify weakest dimension
3. Change the agent (better prompts, different tool, new pipeline stage)
4. Run eval again → compare
5. If better, update baseline. If worse, revert.

This is the same pattern as LLM evals but applied to a multi-stage agent pipeline.
The fixed context means you're measuring the agent's quality, not the input quality.

## Files to Create

1. `plugins/canopy/agents/website-builder.md` — Agent definition
2. `plugins/canopy/skills/website-builder/SKILL.md` — Supporting skill for eval commands
3. `evals/connect/context/product-brief.md` — Connect product context (initial)
4. `evals/connect/context/brand-guidelines.md` — Dimagi brand rules (initial)
5. `evals/connect/context/tone-reference.md` — Connect voice examples
6. `evals/connect/context/reference-sites.md` — Sites we admire
7. `evals/connect/baseline.json` — Initial empty baseline
8. `evals/connect/eval-history.json` — Initial empty history

## Success Criteria

1. `@website-builder generate` produces a Connect landing page from context
2. `@website-builder eval connect` runs the full pipeline and produces scored output
3. Running eval twice with unchanged inputs produces comparable scores (determinism)
4. Changing the prompt measurably changes scores (sensitivity)
5. The eval dataset grows with each run and enables trend analysis

## Dependencies

- Claude Code agent system with `memory: user` support
- /frontend-design plugin (external)
- /design-consultation skill (gstack, external)
- /browse (gstack, external)
- /design-review (gstack, external)
- Connect product collateral (to seed evals/connect/context/)
