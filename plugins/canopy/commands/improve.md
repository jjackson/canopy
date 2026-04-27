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

Read the improve SKILL.md from disk and follow it:

```bash
python3 -c "import json; d=json.load(open('$HOME/.claude/plugins/installed_plugins.json')); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/improve/SKILL.md')"
```

Read that file with the Read tool and follow it step by step, passing the user's argument (if any) to the skill. **Do NOT improvise from memory.** The SKILL.md is the authoritative source.
