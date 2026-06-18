---
description: Product-findings review gate (review_mode human) — post a judged iteration's PRODUCT findings to the review surface as ONE link with per-cluster evidence deep-links (deck #scene-N + video #t=seconds); await implement/skip/defer picks and route them.
argument-hint: <run_id>
allowed-tools: [Read, Write, Bash, Skill]
---

# DDD Product-Findings Review Gate

Post a judged run's PRODUCT findings to the canopy-web review surface as a
single review with evidence deep-links, await the user's per-cluster
implement / skip / defer decisions, and route them.

## Arguments

- `<run_id>` — a judged DDD run identifier from `scripts.ddd.runstate`.

## Process

Read the ddd-findings-review SKILL.md and follow it:

```bash
python3 -c "import json,os; d=json.load(open(os.path.expanduser('~/.claude/plugins/installed_plugins.json'))); print(d['plugins']['canopy@canopy'][0]['installPath'] + '/skills/ddd-findings-review/SKILL.md')"
```

Read that file with the Read tool and follow it step by step.
