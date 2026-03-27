---
description: Review recent sessions, detect stale skills, propose improvements with confidence scores. Use when asked to "review sessions", "session review", "what should I improve", or "analyze recent work".
argument-hint: [<count>|hours <N>|project <name>|auto-improve]
allowed-tools: [Read, Bash, Write, Edit, Glob, Grep, AskUserQuestion, Agent, Skill]
---

# Session Review

Batch-review recent sessions, detect stale skill versions, cross-reference prior
improvement attempts, and produce a ranked findings table with confidence scores.

## Arguments

- `<count>` (integer, default 10) — Number of sessions to review
- `hours <N>` — Time window instead of count
- `project <name>` — Filter to sessions from a specific project
- `auto-improve` — Automatically implement proposals with >= 70% confidence
- Arguments combine: `15 auto-improve`, `hours 48 project canopy`

## Examples

- `/canopy:session-review` — review last 10 sessions, present table
- `/canopy:session-review 20` — review last 20
- `/canopy:session-review hours 48` — last 48 hours
- `/canopy:session-review auto-improve` — review + auto-implement high-confidence proposals
- `/canopy:session-review 15 auto-improve` — 15 sessions + auto-implement

## Routing

All invocations route to the **session-review agent**. There is no skill-only mode —
session review always requires orchestration.

Read the agent definition and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/agents/session-review.md')"
```

Read that file with the Read tool and follow it. The agent handles:
- **Review mode** (default): Fetch → analyze → synthesize → present table → wait for user
- **Auto-improve mode**: Fetch → analyze → synthesize → implement >= 70% confidence proposals
