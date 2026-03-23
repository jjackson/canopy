---
name: brief
description: Generate a strategic brief from recent canopy activity — patterns, success rates, and improvement opportunities
version: 0.1.0
---

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
