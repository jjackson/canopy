---
description: Run a full canopy improvement cycle — analyze sessions, propose improvements, implement via agents
argument-hint: [observe|dry-run]
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, Agent]
---

# Improve

Run a canopy improvement cycle on recent Claude Code sessions.

## Arguments

- No args: full cycle (analyze + propose + implement via agents)
- `observe`: analyze only, write observations
- `dry-run`: analyze + propose, skip implementation

## Process

1. Invoke the `improve` skill
2. The skill orchestrates all phases directly:
   - Discovers unprocessed transcripts
   - Reads and analyzes them in-context (no subprocess calls)
   - Generates proposals in-context
   - Dispatches parallel agents with worktree isolation for implementation
   - Agents create PRs for each improvement
3. Display results with PR links
