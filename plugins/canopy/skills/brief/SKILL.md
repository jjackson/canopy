---
name: brief
description: Generate a strategic brief from recent canopy activity — patterns, success rates, and improvement opportunities
---

## Preamble (run first)

```bash
_CANOPY_UPD=$(bash "$HOME/emdash-projects/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || bash "$HOME/.claude/plugins/marketplaces/canopy/plugins/canopy/scripts/canopy-update-check.sh" 2>/dev/null || true)
case "$_CANOPY_UPD" in UPGRADE_AVAILABLE*) echo "$_CANOPY_UPD" ;; esac
```

If output shows `UPGRADE_AVAILABLE <old> <new>`: tell the user "canopy **v{new}** is available (you're on v{old}). Run `/canopy:update` to upgrade." Then continue with the skill — do not block on the upgrade.

# Brief

Generates a CEO-level strategic brief from recent orchestrator activity. Applies inversion reflex, leverage obsession, and focus-as-subtraction to the pipeline's data.

## Flow

1. Run from the canopy repo working directory:

```bash
uv run canopy brief
```

2. Display the markdown output to the user

## Options

- `--model MODEL`: Model to use (default: sonnet)
- `--budget BUDGET`: Max USD per claude -p call (default: 1.0)

## Rules

- The command invokes `claude -p` internally — may take 30-60 seconds
- If `claude -p` fails, it falls back to a simple digest from local data
- The brief draws from: recent run logs, detected patterns, pending observations, and proposal success rates
