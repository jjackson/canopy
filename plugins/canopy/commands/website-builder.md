---
description: >
  Build marketing websites from product context, or run evaluation suites
  to measure and improve generation quality. Uses persistent memory for
  brand context. Use when asked to "build a website", "generate a page",
  "eval website", or "website-builder".
argument-hint: [generate|eval <product>|eval <product> --update-baseline|eval <product> --history|eval <product> --compare <run1> <run2>]
allowed-tools: [Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion, Agent, Skill]
---

# Website Builder

Build marketing websites from product context or evaluate generation quality.

## Arguments

- `generate` (default) — Run the full generation pipeline from ./context/
- `eval <product>` — Run eval suite against fixed context in evals/<product>/
- `eval <product> --update-baseline` — Set most recent run as baseline
- `eval <product> --history` — Show score trends
- `eval <product> --compare <run1> <run2>` — Compare two runs
- No args: same as `generate`

## Process

For `generate`:
1. Check if this is being run as the `website-builder` agent (has memory).
   If yes, follow the agent's generate pipeline.
2. If running as a skill (no agent memory), read ./context/ directly and
   run the pipeline inline.

For `eval`:
1. Invoke the `website-builder` skill
2. Follow the eval workflow for the specified product
