---
description: Narrative-agreement gate (concept_change) — post the demo story arc for explicit user agreement before any rendering or building. On rethink loops back to /ddd-spec; on agree/edit the narrative is locked in and ddd-run may proceed.
argument-hint: <spec_path> <run_id>
allowed-tools: [Read, Write, Bash, Skill]
---

# DDD Narrative Review Gate

Post the demo narrative to the review surface for the user's explicit agreement.
This is the missing gate between ddd-spec-qa and ddd-run.

## Arguments

- `<spec_path>` — path to the unified spec YAML (`docs/walkthroughs/<feature>.yaml`).
- `<run_id>` — the DDD run identifier from `scripts.ddd.runstate`.

## Process

Read the ddd-narrative-review SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-narrative-review/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
