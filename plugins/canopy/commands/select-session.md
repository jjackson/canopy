---
description: Menu-driven session picker — select a project, browse session history, and analyze a chosen session
argument-hint: [hours]
allowed-tools: [Read, Bash, AskUserQuestion]
---

# Select Session

Browse and analyze recent Claude Code sessions interactively.

## Arguments

- `hours` (optional): Time window for session search. Default: 24. Example: `/select-session 72`

## Process

1. Invoke the `select-session` skill
2. Follow the interactive flow: project selection → session selection → analysis
3. Display the analysis output
