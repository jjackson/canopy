---
description: Run a full canopy improvement cycle — analyze sessions, propose and implement improvements
argument-hint: [observe|dry-run]
allowed-tools: [Read, Bash, Write, Edit, Agent]
---

# Improve

Run a canopy improvement cycle on recent Claude Code sessions.

## Arguments

- No args: full cycle (analyze + propose + implement)
- `observe`: analyze only
- `dry-run`: analyze + propose, skip implementation

## Process

1. Invoke the `improve` skill
2. Run the appropriate `uv run canopy improve` command
3. Display results
