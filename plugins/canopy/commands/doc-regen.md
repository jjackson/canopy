---
description: Audit project docs for staleness and coverage gaps, then regenerate CLAUDE.md
argument-hint: [--apply]
allowed-tools: [Read, Glob, Grep, Bash, Agent, Write, Edit, AskUserQuestion]
---

# Doc Regeneration

Audit project documentation against actual project state and regenerate CLAUDE.md.

## Arguments

- `--apply` (optional): Create a branch and PR with the regenerated docs. Without this flag, outputs to `docs/.dry-run/` for review.

## Process

1. Invoke the `doc-regeneration` skill
2. Execute all four phases (Read Everything → Analyze → Produce Output → Deliver)
3. Present the review report to the user
