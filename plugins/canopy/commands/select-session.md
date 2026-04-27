---
description: Menu-driven session picker — select a project, browse history, analyze, propose fixes, and implement
argument-hint: [hours]
allowed-tools: [Read, Bash, Write, Edit, Agent, AskUserQuestion]
---

# Select Session

Browse recent sessions, analyze friction, propose fixes, and implement improvements.

## Arguments

- `hours` (optional): Time window for session search. Default: 24. Example: `/select-session 72`

## Process

Read the select-session SKILL.md from disk and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/select-session/SKILL.md')"
```

Read that file with the Read tool and follow it step by step, passing the `hours` argument (if provided) to the skill. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.
