---
description: Run a PM scout cycle on the current project — explore, propose improvements, learn
argument-hint: [lens]
allowed-tools: [Read, Glob, Grep, Bash, Agent, Write, Edit, AskUserQuestion]
---

# PM Scout

Run a product management scout cycle on the current project.

## Arguments

- `lens` (optional): The exploration lens to use. One of: user-value, adoption-blockers, integration-depth, trust-reliability, tech-debt. If not specified, rotate from the last lens used — determine this by parsing the filename of the most recent file in `.claude/pm/runs/` (format: `YYYY-MM-DD-<lens>.md`). Pick the next lens in the list above. If no runs exist yet, start with `user-value`.

## Process

1. Invoke the `product-management` skill
2. Execute Phase 1 (Scout) using the specified lens
3. Present findings in the Phase 2 (Propose) format
4. Wait for user disposition on each proposal
5. Execute Phase 6 (Learn) — write run log and update learnings
6. Evaluate for universal improvements to the skill itself
