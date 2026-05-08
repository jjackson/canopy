---
description: Run a PM scout cycle on the current project — explore, propose improvements, learn
argument-hint: [lens]
allowed-tools: [Read, Glob, Grep, Bash, Agent, Write, Edit, AskUserQuestion]
---

# PM Scout

Run a product management scout cycle on the current project.

## Arguments

- `lens` (optional): The exploration lens to use. One of: user-value, adoption-blockers, integration-depth, trust-reliability, tech-debt. If not specified, rotate from the last lens used — first compute `PLUGIN_PATH=$(python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'])")`, then resolve `CANOPY_PM_DIR=$(bash "$PLUGIN_PATH/skills/product-management/scripts/resolve_pm_dir.sh")`, then parse the filename of the most recent file in `$CANOPY_PM_DIR/runs/` (format: `YYYY-MM-DD-<lens>.md`). Pick the next lens in the list above. If no runs exist yet, start with `user-value`.

## Process

1. Invoke the `product-management` skill
2. Execute Phase 1 (Scout) using the specified lens
3. Present findings in the Phase 2 (Propose) format
4. Wait for user disposition on each proposal
5. Execute Phase 6 (Learn) — write run log and update learnings
6. Evaluate for universal improvements to the skill itself
